import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))

# import os
from multiprocessing import Lock

import monai
import monai.transforms as mt
import numpy as np
import torch
from autopet3.datacentric.transforms import get_transforms
from autopet3.datacentric.utils import get_file_dict_nn, read_split
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm


class ResampleDataset(Dataset):
    def __init__(
        self,
        data_dir: str,
        split_dir: str, # 추가
        save_path: str,
        transform: mt.Compose,
        fold: int = 0, # 추가
        samples_per_file: int = 15,
        seed: int = 42,
        resume: bool = False,
    ) -> None:
        """Initialize the class with the provided parameters.
        Args:
            data_dir (str): Path to the directory containing the data.
            save_path (str): Path to save the processed data.
            transform (monai composable): Transformation function to apply to the data.
            samples_per_file (int): Number of samples per file.
            seed (int): Seed for reproducibility.
            resume (bool): Flag indicating whether to resume preprocessing.

        """
        monai.utils.set_determinism(seed=seed)
        np.random.seed(seed)

        split_data = read_split(split_dir, fold)
        train_val_data = split_data["train"] + split_data["val"]

        # self.files = get_file_dict_nn(data_dir, train_val_data, suffix=".nii.gz")
        self.transform = transform
        self.destination = save_path
        self.root = data_dir
        self.samples_per_file = samples_per_file

        if resume:
            valid_files = self.resume_preprocessing()
            train_val_data = list(set(train_val_data) - set(valid_files))

        self.files = get_file_dict_nn(data_dir, train_val_data, suffix=".nii.gz")
        self.lock = Lock()

    def __len__(self):
        return len(self.files)

    def __getitem__(self, idx):
        file_path = self.files[idx]
        for i in range(self.samples_per_file):
            image, label = self.transform(file_path)
            label_name = str(file_path["label"]).replace(".nii.gz", "").split("/")[-1]
            label_base = os.path.basename(label_name) # 추가
            output_path = os.path.join(self.destination, f"{label_base}_{i:03d}.npz") # 수정
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with self.lock:
                np.savez_compressed(output_path, input=image.numpy(), label=label.numpy())
        return image, label

    def resume_preprocessing(self):
        unique_files, counts = np.unique(
            ["_".join(i.split("_")[:-1]) for i in os.listdir(self.destination)], return_counts=True
        )
        valid_files = list(unique_files[counts == self.samples_per_file])
        for j, i in tqdm(enumerate(valid_files), desc=f"Resuming preprocessing. Validate {len(valid_files)} files"):
            test_file = os.path.join(self.destination, f"{i}_{self.samples_per_file - 1:03d}.npz")
            # Load and process data
            data = np.load(test_file)
            try:
                image = torch.from_numpy(data["input"])
                label = torch.from_numpy(data["label"])
                valid_files.append(test_file)
            except Exception:
                valid_files.pop(j)

        print(f"Found {len(valid_files)} valid files!")
        return valid_files


def test_integrity(dir_path):
    for filename in tqdm(os.listdir(dir_path)):
        file_path = os.path.join(dir_path, filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File '{filename}' does not exist in directory.")

        # Load data
        data = np.load(file_path)
        try:
            image = torch.from_numpy(data["input"])
            label = torch.from_numpy(data["label"])
        except Exception as e:
            print("Error occurred:", e)
            print(filename)


if __name__ == "__main__":
    challenge_root_path = "G:\\joohyun\\research\\AutoPET Challenge 2024"
    data_path = os.path.join(challenge_root_path, "data")
    data_test_path = os.path.join(data_path, "test")
    data_train_path = os.path.join(data_path, "train")
    data_train_sampled_path = os.path.join(data_train_path, "sampled")
    data_train_randomsampled_path = os.path.join(data_train_path, "randomsampled")
    preprocessed_path = os.path.join(challenge_root_path, "preprocessed")
    json_path = os.path.join(challenge_root_path, "json")
    train_fold_sampled_json_path = os.path.join(json_path, "train_fold_sampled_data.json")
    train_fold_final_path = os.path.join(json_path, "train_fold_final_data.json")
    
    root = data_train_path
    split = train_fold_final_path
    dest = preprocessed_path
    fold = 0
    worker = 3
    samples_per_file = 10
    seed = 42

    transform = get_transforms("train", target_shape=(128, 160, 112), resample=True)
    ds = ResampleDataset(root, split, dest, transform, fold=0, samples_per_file=samples_per_file, seed=seed, resume=False)

    dataloader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=worker)
    for _ in tqdm(dataloader, total=len(dataloader)):
        pass
    test_integrity(dest)
