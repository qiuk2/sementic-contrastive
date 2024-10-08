import glob
import random

import numpy as np
from torch.utils.data import Dataset
import torchvision.transforms as transforms
import os
from PIL import Image
import json
from pycocotools import mask as mask_utils
import torch
from torch.nn import functional as F
from tqdm import tqdm

def process_anns(anns, image_size, colormap):
    mask = np.zeros((image_size, image_size, 3))
    for i, ann in enumerate(anns):
        if ann['area'] < 5000:
            continue
        m = ann['segmentation']
        m = mask_utils.decode(m)
        X, Y = m.shape[1], m.shape[0]
        index = np.where(m == 1)
        x = int(np.mean(index[1]) // (X / 11))
        y = int(np.mean(index[0]) // (Y / 11))
        m = m.astype(bool)
        assert x * y < 124
        mask[m] = colormap[(x * y) % len(colormap)]
    return mask

def create_color_map():
    color_map = []
    for r in [0, 64, 128, 192, 255]:
        for g in [0, 64, 128, 192, 255]:
            for b in [0, 64, 128, 192, 255]:
                color_map.append([r, g, b])
    return np.array(color_map)[1:]


def find_classes(directory):
    """Finds the class folders in a dataset.

    See :class:`DatasetFolder` for details.
    """
    classes = sorted(entry.name for entry in os.scandir(directory) if entry.is_dir())
    if not classes:
        raise FileNotFoundError(f"Couldn't find any class folder in {directory}.")

    class_to_idx = {cls_name: i for i, cls_name in enumerate(classes)}
    return classes, class_to_idx

class ImagenetDDataset(Dataset):
    def __init__(self, root: str, split: str = "train", transform=None, image_size=256,
                 separator=False, val_cond='depth', **kwargs):

        self.transforms = transform
        self.split = split
        self.load_dataset(root)
        classes, class_to_idx = find_classes(os.path.join(root, split))
        self.cond = {'depth': self.depth_paths}
        self.cond_idx = {'depth': 2}
        self.class_to_idx = class_to_idx
        print('Use ImageFolder Class to IDX')
        self.image_size = image_size
        self.separator = separator
        self.colormap = create_color_map()
        print(f'ImagenetC dataset init: total images '
              f'{len(self.depth_paths)}')
        if self.split == 'val':
            self.val_cond = val_cond
            print(f'Warning: Only use {self.val_cond} during the evaluation')

    def load_dataset(self, root):
        cond_info_path = os.path.join(root, f'{self.split}_cond_info_depth.json')

        if os.path.exists(cond_info_path):
            print('load ImageNetC from json')
            with open(cond_info_path, 'r') as file:
                cond_info = json.load(file)
            self.depth_paths = cond_info['depth']
            print('depth')
            print(len(self.depth_paths))
        else:
            print('load ImageNetM from glob')
            self.depth_paths = sorted(glob.glob(os.path.join(root, f"{self.split}_depth/" "*", "*.jpeg")))
            colormap = create_color_map()
            for paths in [self.depth_paths]:
                with tqdm(total=len(paths)) as pbar:
                    for path in paths:
                        size = os.stat(path).st_size
                        pbar.update(1)
                        if size < 1000:
                            try:
                                if 'mask' in path:
                                    with open(path, 'r') as f:
                                        mask_info = json.load(f)
                                    mask = process_anns(mask_info, 512, colormap).astype(np.uint8)
                                    mask = Image.fromarray(mask)
                                else:
                                    mask = Image.open(path)
                            except:
                                print(path)
                                paths.remove(path)
            data = {
                'depth': self.depth_paths,
            }
            with open(cond_info_path, 'w') as file:
                json.dump(data, file)


    def __len__(self):
        return len(self.depth_paths)

    def __getitem__(self, index: int):
        cond_type = random.choices(['mask', 'canny', 'normal', 'depth'], [0, 0, 0, 1], k=1)[0]
        # TODO: add mask val dataset
        if self.split == 'val':
            cond_type = self.val_cond
            # print(f'Warning: Only use {cond_type} during the evaluation')

        cond_path = self.cond[cond_type][index % len(self.cond[cond_type])]
        image_path = cond_path.replace(self.split+'_'+cond_type, self.split).replace('.json', '.JPEG').replace('.jpeg', '.JPEG')
        cls = self.class_to_idx[(image_path.split('/')[-2])]
        image = Image.open(image_path).convert('RGB')

        if cond_type == 'mask':
            with open(cond_path, 'r') as f:
                mask_info = json.load(f)
            mask = process_anns(mask_info, 512, self.colormap).astype(np.uint8)  # 512 is fixed during the labelling
            cond = Image.fromarray(mask)
        else:
            cond = Image.open(cond_path).convert('RGB')
        cond = cond.resize(image.size)

        if self.transforms:
            image, cond = self.transforms(image, cond)

        sample = {'image': image, 'mask': cond, 'cls': cls, 'type': torch.tensor(self.cond_idx[cond_type])}
        # print(cond_path)
        return sample


if __name__ == '__main__':
    root= '../ImageNet2012/'
    cond_info_path = os.path.join(root, 'cond_info.json')
    if os.path.exists(cond_info_path):
        print('load ImageNetC from json')
        with open(cond_info_path, 'r') as file:
            cond_info = json.load(file)
            mask_paths = cond_info['mask']
            canny_paths = cond_info['canny']
            depth_paths = cond_info['depth']
            normal_paths = cond_info['normal']

    from tqdm import tqdm
    with tqdm(total=len(normal_paths)) as pbar:
        for path in normal_paths:
            try:
                img = Image.open(path)#.convert('RGB')
            except:
                print(path)
            # img_path = path.replace('normal', 'train').replace('.json', '.JPEG').replace('.jpeg', '.JPEG')
            #     with open(mask_path, 'r') as f:
            #         mask_info = json.load(f)
            #     mask = process_anns(mask_info, 512, colormap).astype(np.uint8)  # 512 is fixed during the labelling
            #     mask = Image.fromarray(mask)
            #     mask.save('mask.png')
            #     print(mask.path)
            # except:
            #     fail_list.append(mask_path)
            #     print(mask_path)

            pbar.update(1)
    # for path in fail_list:
    #     os.system(f'rm {path}')
