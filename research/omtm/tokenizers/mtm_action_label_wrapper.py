# MIT License

# Copyright (c) 2023 Meta Research

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import os
from typing import Dict, Tuple

import hydra
import numpy as np
import torch
import torch.nn as nn
from omegaconf import OmegaConf
from torch.utils.data.dataloader import DataLoader

from research.omtm.models.omtm_model import omtm
from research.omtm.tokenizers.base import Tokenizer, TokenizerManager


def get_omtm_model(
    path: str,
) -> Tuple[omtm, TokenizerManager, Dict[str, Tuple[int, int]]]:
    def _get_dataset(dataset, traj_length):
        return hydra.utils.call(dataset, seq_steps=traj_length)

    # find checkpoints in the directory
    steps = []
    names = []
    paths_ = os.listdir(path)
    for name in [os.path.join(path, n) for n in paths_ if "pt" in n]:
        step = os.path.basename(name).split("_")[-1].split(".")[0]
        steps.append(int(step))
        names.append(name)
    ckpt_path = names[np.argmax(steps)]

    hydra_cfg = OmegaConf.load(os.path.join(path, ".hydra/config.yaml"))
    cfg = hydra.utils.instantiate(hydra_cfg.args)
    hydra_cfg.dataset.train_max_size = 10000
    train_dataset, _ = _get_dataset(hydra_cfg.dataset, cfg.traj_length)
    tokenizers: Dict[str, Tokenizer] = {
        k: hydra.utils.call(v, key=k, train_dataset=train_dataset)
        for k, v in hydra_cfg.tokenizers.items()
    }
    tokenizer_manager = TokenizerManager(tokenizers)
    discrete_map: Dict[str, bool] = {}
    for k, v in tokenizers.items():
        discrete_map[k] = v.discrete
    train_loader = DataLoader(
        train_dataset,
        # shuffle=True,
        pin_memory=True,
        batch_size=cfg.batch_size,
        num_workers=cfg.n_workers,
    )
    train_batch = next(iter(train_loader))
    tokenized = tokenizer_manager.encode(train_batch)
    data_shapes = {}
    for k, v in tokenized.items():
        data_shapes[k] = v.shape[-2:]

    model_config = hydra.utils.instantiate(hydra_cfg.model_config)
    model = omtm(data_shapes, cfg.traj_length, model_config)
    model.load_state_dict(torch.load(ckpt_path)["model"])
    model.eval()

    # freeze the model
    for param in model.parameters():
        param.requires_grad = False

    return model, tokenizer_manager, data_shapes


class omtmActionLabelWrapper(nn.Module):
    """Dummy tokenizer for trajectories that are already discrete."""

    def __init__(self, path: str, device: str):
        super().__init__()
        self.path = path
        self.omtm_model, self.tokenizer_manager, self.data_shapes = get_omtm_model(path)
        self.device = device
        self.omtm_model.to(device)

    def relabel_action(
        self, trajectories: Dict[str, torch.Tensor]
    ) -> Dict[str, torch.Tensor]:
        """Relabels the action labels of a trajectory.

        Args:
            trajectories: A dictionary of trajectories.

        Returns:
            trajectories with the actions relabeled.
        """
        trajectories = self.tokenizer_manager.encode(trajectories)
        traj_length = self.omtm_model.traj_length
        masks = {
            "states": torch.ones(traj_length, device=self.device),
            "actions": torch.zeros(traj_length, device=self.device),
            "returns": torch.ones(traj_length, device=self.device),
        }
        with torch.no_grad():
            relabeled = self.omtm_model(trajectories)

        decoded = self.tokenizer_manager.decode(relabeled)
        # replace actions
        trajectories["actions"] = decoded["actions"]

        return trajectories
