#!/usr/bin/env python3
"""D2 — a CAUSAL streaming KWS model for 'hey m' (streaming-native inference).

Unlike the windowed DS-CNN (which re-runs a full [1,100,40] inference every hop = ~10x
redundant conv compute), this model processes ONE log-mel frame at a time with per-layer
ring-buffer state, emitting a wake/no-wake logit per frame. Its causal receptive field
(stacked dilated causal convs) replaces the 100-frame window.

Correctness crux (self-tested in __main__): the frame-by-frame `step()` path must produce
outputs IDENTICAL to the full-clip `forward_frames()` path. If that holds, streaming is a
drop-in, cheaper equivalent — you pay per-frame conv cost instead of per-hop window cost.

Training reuses the fixed [N,100,40] window cache (each window = a clip; temporal max-pool of
the per-frame positive logit = the clip score). Streaming inference runs frame-by-frame.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


class StreamCausalConv(nn.Module):
    """Depthwise-separable causal Conv1d over time (channels = features). Streamable via a
    ring-buffer state of the last (k-1)*dilation inputs."""
    def __init__(self, ch, k=3, dilation=1):
        super().__init__()
        self.buf_len = (k - 1) * dilation
        self.dw = nn.Conv1d(ch, ch, k, dilation=dilation, groups=ch)   # depthwise, no pad
        self.pw = nn.Conv1d(ch, ch, 1)                                  # pointwise mix
        self.bn = nn.BatchNorm1d(ch)

    def forward(self, x):                       # [B, ch, T] -> [B, ch, T]  (causal left-pad)
        y = F.pad(x, (self.buf_len, 0))
        y = self.pw(self.dw(y))
        return F.relu(self.bn(y) + x)           # residual

    def init_state(self, B, device):
        return torch.zeros(B, self.dw.in_channels, self.buf_len, device=device)

    def step(self, x_t, state):                 # x_t [B,ch,1], state [B,ch,buf_len]
        buf = torch.cat([state, x_t], dim=2)    # [B,ch, buf_len+1]
        y = self.pw(self.dw(buf))               # dw over buf_len+1 -> length 1
        y = F.relu(self.bn(y) + x_t)
        return y, buf[:, :, 1:]                 # drop oldest -> new state


class StreamingKWS(nn.Module):
    def __init__(self, mean, std, n_mels=40, ch=48, n_classes=2, k=3,
                 dilations=(1, 2, 4, 8, 16, 32)):
        super().__init__()
        self.register_buffer("mean", torch.tensor(np.asarray(mean), dtype=torch.float32))
        self.register_buffer("std", torch.tensor(np.asarray(std), dtype=torch.float32))
        self.inproj = nn.Conv1d(n_mels, ch, 1)
        self.blocks = nn.ModuleList([StreamCausalConv(ch, k, d) for d in dilations])
        self.head = nn.Conv1d(ch, n_classes, 1)
        self.receptive_field = 1 + sum((k - 1) * d for d in dilations)

    def _norm(self, x):                         # x [B,T,40] -> [B,40,T] normalized
        x = (x - self.mean) / self.std
        return x.transpose(1, 2)

    def forward_frames(self, x):                # [B,T,40] -> [B,T,n_classes] per-frame logits
        h = self.inproj(self._norm(x))
        for b in self.blocks:
            h = b(h)
        return self.head(h).transpose(1, 2)

    def forward(self, x):                       # [B,T,40] -> [B,n_classes] clip logits
        fl = self.forward_frames(x)             # temporal max-pool the positive evidence
        return fl.max(dim=1).values

    # ---- streaming API (one frame at a time) ----
    def init_states(self, B=1, device="cpu"):
        return [b.init_state(B, device) for b in self.blocks]

    def step(self, frame, states):              # frame [B,40] -> logit [B,n_classes], states
        x = ((frame - self.mean) / self.std).unsqueeze(2)   # [B,40,1]
        h = self.inproj(x)
        new = []
        for b, s in zip(self.blocks, states):
            h, s2 = b.step(h, s)
            new.append(s2)
        return self.head(h).squeeze(2), new


def _selftest():
    torch.manual_seed(0)
    mean = np.zeros(40, np.float32); std = np.ones(40, np.float32)
    m = StreamingKWS(mean, std).eval()
    T = 120
    x = torch.randn(1, T, 40)
    with torch.no_grad():
        full = m.forward_frames(x)              # [1,T,2]
        st = m.init_states(1)
        outs = []
        for t in range(T):
            lo, st = m.step(x[:, t, :], st)
            outs.append(lo)
        stream = torch.stack(outs, dim=1)        # [1,T,2]
    diff = (full - stream).abs().max().item()
    print(f"receptive_field={m.receptive_field} frames  params={sum(p.numel() for p in m.parameters())}")
    print(f"max |forward_frames - step| = {diff:.2e}  -> {'EQUIVALENT' if diff < 1e-4 else 'MISMATCH!!'}")
    return diff < 1e-4


if __name__ == "__main__":
    import sys
    sys.exit(0 if _selftest() else 1)
