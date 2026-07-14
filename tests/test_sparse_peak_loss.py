import sys
import torch
import torch.nn.functional as F
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from atabey.experiments.cnn_advisor import SparsePeakLoss

def test_sparse_peak_loss_zero_invariant():
    print("Testing SparsePeakLoss zero-loss invariant for unannotated regions...")
    
    # 1. Create a dummy prediction tensor (B=1, C=1, Z=10, Y=10, X=10)
    # Let's say the network predicts 100% confidence (logits = +10) everywhere
    pred = torch.full((1, 1, 10, 10, 10), 10.0, dtype=torch.float32, requires_grad=True)
    
    # 2. Provide NO ground truth centers (empty list)
    gt_centers = []
    
    # 3. Instantiate loss
    loss_fn = SparsePeakLoss(window_shape=(5, 3, 3))
    
    # 4. Compute loss
    loss = loss_fn(pred, gt_centers)
    print(f"Loss with 0 annotations: {loss.item()}")
    
    # 5. Check gradients
    loss.backward()
    
    max_grad = pred.grad.abs().max().item()
    print(f"Max gradient absolute value: {max_grad}")
    
    if loss.item() == 0.0 and max_grad == 0.0:
        print("[PASS] Unannotated voxels contribute exactly 0.0 to loss and gradient.")
    else:
        print("[FAIL] Zero invariant violated!")
        sys.exit(1)
        
    print("\nTesting SparsePeakLoss window boundary invariant...")
    pred2 = torch.full((1, 1, 10, 10, 10), 10.0, dtype=torch.float32, requires_grad=True)
    gt_centers2 = [(0, 5, 5, 5)] # one annotation at Z=5, Y=5, X=5
    
    loss2 = loss_fn(pred2, gt_centers2)
    loss2.backward()
    
    grad = pred2.grad[0, 0] # Shape: (10, 10, 10)
    
    # Check that gradient is exactly zero outside the 5x3x3 window
    # Window centered at 5,5,5:
    # Z: 5 - 2 to 5 + 2 = [3, 4, 5, 6, 7]
    # Y: 5 - 1 to 5 + 1 = [4, 5, 6]
    # X: 5 - 1 to 5 + 1 = [4, 5, 6]
    
    mask = torch.ones_like(grad, dtype=torch.bool)
    mask[3:8, 4:7, 4:7] = False # Set inside-window to False
    
    grad_outside = grad[mask]
    grad_inside = grad[~mask]
    
    if grad_outside.abs().max().item() == 0.0 and grad_inside.abs().max().item() > 0.0:
        print("[PASS] Gradient only flows inside the 5x3x3 local window.")
    else:
        print(f"[FAIL] Window invariant violated! Max grad outside: {grad_outside.abs().max().item()}, Max grad inside: {grad_inside.abs().max().item()}")
        sys.exit(1)

if __name__ == "__main__":
    test_sparse_peak_loss_zero_invariant()
