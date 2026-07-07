#!/usr/bin/env python3
"""KWS model zoo for the AURA robustness head-to-head (ROBUSTNESS_IMPROVEMENTS #5, ADR-001).

Three architectures behind one interface. All: input [B, 100, 40] raw log-Mel; fold
per-mel-bin normalization ((x-mean)/std) into the graph as registered buffers (so the C++
side feeds raw features); output [B, num_classes] logits. All export cleanly to ONNX via the
legacy exporter (standard Conv2d/BN/ReLU/pool/linear only).

Orientation: x [B,100,40] (time, freq) -> [B,1,40,100] (C=1, F=40, T=100) for the conv nets.
"""
import torch
import torch.nn as nn


class _Norm(nn.Module):
    """Folded (x-mean)/std over the 40 mel bins, then reshape to [B,1,F,T]."""
    def __init__(self, mean, std):
        super().__init__()
        self.register_buffer("mean", torch.as_tensor(mean, dtype=torch.float32))
        self.register_buffer("std", torch.as_tensor(std, dtype=torch.float32))

    def forward(self, x):                 # x: [B, T=100, F=40]
        x = (x - self.mean) / self.std
        return x.transpose(1, 2).unsqueeze(1)   # -> [B, 1, F=40, T=100]


# ---------------- CNN (improved baseline) ----------------
class CNN(nn.Module):
    def __init__(self, mean, std, num_classes, width=24):
        super().__init__()
        self.norm = _Norm(mean, std)

        def blk(ci, co):
            return nn.Sequential(nn.Conv2d(ci, co, 3, padding=1), nn.BatchNorm2d(co),
                                 nn.ReLU(), nn.MaxPool2d(2))
        self.net = nn.Sequential(blk(1, width), blk(width, width * 2), blk(width * 2, width * 2))
        self.head = nn.Linear(width * 2, num_classes)

    def forward(self, x):
        x = self.norm(x)
        x = self.net(x)
        x = x.mean(dim=(2, 3))
        return self.head(x)


# ---------------- BC-ResNet (broadcasted residual) ----------------
class _BCResBlock(nn.Module):
    def __init__(self, c_in, c_out, stride=1, dilation=1):
        super().__init__()
        self.transition = (c_in != c_out) or (stride != 1)
        if self.transition:
            # transition handles the channel change AND the freq downsampling, so the
            # identity and main paths stay the same freq size for the residual add.
            self.tr = nn.Sequential(nn.Conv2d(c_in, c_out, 1, stride=(stride, 1), bias=False),
                                    nn.BatchNorm2d(c_out), nn.ReLU())
        # frequency-depthwise 2D conv (stride handled by the transition, so stride=1 here)
        self.f2 = nn.Sequential(
            nn.Conv2d(c_out, c_out, (3, 1), padding=(1, 0), groups=c_out, bias=False),
            nn.BatchNorm2d(c_out))
        # temporal-depthwise 1D conv on freq-averaged signal, then pointwise
        self.f1 = nn.Sequential(
            nn.Conv2d(c_out, c_out, (1, 3), padding=(0, dilation), dilation=(1, dilation),
                      groups=c_out, bias=False),
            nn.BatchNorm2d(c_out), nn.ReLU(),
            nn.Conv2d(c_out, c_out, 1, bias=False))
        self.relu = nn.ReLU()

    def forward(self, x):
        if self.transition:
            x = self.tr(x)
        identity = x
        out = self.f2(x)                          # [B,C,F,T]
        aux = out.mean(dim=2, keepdim=True)       # broadcast: avg over freq -> [B,C,1,T]
        aux = self.f1(aux)
        out = out + aux                           # add broadcast back over freq
        return self.relu(out + identity)


class BCResNet(nn.Module):
    def __init__(self, mean, std, num_classes, c=16):
        super().__init__()
        self.norm = _Norm(mean, std)
        self.stem = nn.Sequential(nn.Conv2d(1, c, (3, 3), padding=1), nn.BatchNorm2d(c), nn.ReLU())
        self.blocks = nn.Sequential(
            _BCResBlock(c, c),
            _BCResBlock(c, c * 2, stride=2),        # downsample freq
            _BCResBlock(c * 2, c * 2, dilation=2),
            _BCResBlock(c * 2, c * 2, stride=2),
            _BCResBlock(c * 2, c * 2, dilation=2),
        )
        self.head = nn.Linear(c * 2, num_classes)

    def forward(self, x):
        x = self.norm(x)
        x = self.stem(x)
        x = self.blocks(x)
        x = x.mean(dim=(2, 3))
        return self.head(x)


# ---------------- DS-CNN (depthwise-separable, MobileNet/MatchboxNet family) ----------------
class _DSBlock(nn.Module):
    def __init__(self, c_in, c_out, stride=1):
        super().__init__()
        self.dw = nn.Sequential(
            nn.Conv2d(c_in, c_in, 3, stride=stride, padding=1, groups=c_in, bias=False),
            nn.BatchNorm2d(c_in), nn.ReLU())
        self.pw = nn.Sequential(
            nn.Conv2d(c_in, c_out, 1, bias=False), nn.BatchNorm2d(c_out), nn.ReLU())

    def forward(self, x):
        return self.pw(self.dw(x))


class DSCNN(nn.Module):
    def __init__(self, mean, std, num_classes, c=32):
        super().__init__()
        self.norm = _Norm(mean, std)
        self.stem = nn.Sequential(nn.Conv2d(1, c, 3, stride=2, padding=1),
                                  nn.BatchNorm2d(c), nn.ReLU())
        self.net = nn.Sequential(
            _DSBlock(c, c), _DSBlock(c, c * 2, stride=2),
            _DSBlock(c * 2, c * 2), _DSBlock(c * 2, c * 2, stride=2))
        self.head = nn.Linear(c * 2, num_classes)

    def forward(self, x):
        x = self.norm(x)
        x = self.stem(x)
        x = self.net(x)
        x = x.mean(dim=(2, 3))
        return self.head(x)


def build_model(arch, mean, std, num_classes):
    arch = arch.lower()
    if arch == "cnn":
        return CNN(mean, std, num_classes)
    if arch == "bcresnet":
        return BCResNet(mean, std, num_classes)
    if arch == "dscnn":
        return DSCNN(mean, std, num_classes)
    raise ValueError(f"unknown arch: {arch}")


def param_count(model):
    return sum(p.numel() for p in model.parameters())
