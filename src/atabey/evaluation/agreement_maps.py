import numpy as np
from typing import List, Tuple
from collections import defaultdict
import scipy.spatial

def compute_multi_source_agreement(
    adaptive_points_um: List[Tuple[float, float, float]],
    cfar_points_um: List[Tuple[float, float, float]],
    cnn_points_um: List[Tuple[float, float, float]],
    matching_radius_um: float = 7.0,
    min_agreement: int = 2
) -> Tuple[List[Tuple[float, float, float]], List[Tuple[float, float, float]]]:
    """
    Triangulates detections from three independent sources to find high-confidence points.
    
    Args:
        adaptive_points_um: (Z, Y, X) physical coordinates from adaptive baseline
        cfar_points_um: (Z, Y, X) physical coordinates from CFAR+watershed
        cnn_points_um: (Z, Y, X) physical coordinates from CNN-advisor
        matching_radius_um: Maximum distance to consider points as referring to the same object
        min_agreement: Minimum number of sources that must agree (e.g. 2 of 3)
        
    Returns:
        high_confidence_points: List of (Z, Y, X) centroids of clusters with >= min_agreement sources
        flagged_points: List of (Z, Y, X) centroids of clusters with < min_agreement sources
    """
    
    all_points = []
    source_labels = []
    
    for p in adaptive_points_um:
        all_points.append(p)
        source_labels.append(0)
        
    for p in cfar_points_um:
        all_points.append(p)
        source_labels.append(1)
        
    for p in cnn_points_um:
        all_points.append(p)
        source_labels.append(2)
        
    if not all_points:
        return [], []
        
    points_array = np.array(all_points, dtype=float)
    
    # Use KDTree and connected components to avoid O(N^2) memory from pdist
    import scipy.sparse
    from scipy.spatial import cKDTree
    
    # If only 1 point total
    if len(points_array) == 1:
        if min_agreement <= 1:
            return [tuple(points_array[0])], [], {'cat_a_cnn_completed_pair': 0, 'cat_b_cnn_joined_existing': 0, 'cnn_isolated_flagged': 0, 'original_adapt_cfar_only': 0}
        else:
            return [], [tuple(points_array[0])], {'cat_a_cnn_completed_pair': 0, 'cat_b_cnn_joined_existing': 0, 'cnn_isolated_flagged': 0, 'original_adapt_cfar_only': 0}
            
    # Find all pairs within the matching radius
    tree = cKDTree(points_array)
    pairs = tree.query_pairs(matching_radius_um)
    
    # Form sparse adjacency matrix
    if pairs:
        pairs_arr = np.array(list(pairs), dtype=np.int32)
        row_ind = pairs_arr[:, 0]
        col_ind = pairs_arr[:, 1]
    else:
        row_ind, col_ind = [], []
        
    n = len(points_array)
    # Add self-loops to ensure all nodes are in the graph
    if len(row_ind) > 0:
        row = np.concatenate([row_ind, col_ind, np.arange(n, dtype=np.int32)])
        col = np.concatenate([col_ind, row_ind, np.arange(n, dtype=np.int32)])
    else:
        row = np.arange(n, dtype=np.int32)
        col = np.arange(n, dtype=np.int32)
    data = np.ones(len(row), dtype=int)
    
    graph = scipy.sparse.csr_matrix((data, (row, col)), shape=(n, n))
    
    # Extract flat clusters
    n_components, cluster_ids = scipy.sparse.csgraph.connected_components(csgraph=graph, directed=False, return_labels=True)
    
    # Group by cluster
    clusters = defaultdict(list)
    for idx, cid in enumerate(cluster_ids):
        clusters[cid].append(idx)
        
    high_confidence_points = []
    flagged_points = []
    
    stats = {
        'cat_a_cnn_completed_pair': 0,
        'cat_b_cnn_joined_existing': 0,
        'cnn_isolated_flagged': 0,
        'original_adapt_cfar_only': 0
    }
    
    for cid, indices in clusters.items():
        unique_sources = set(source_labels[idx] for idx in indices)
        
        # Calculate anchor of this cluster (prefer CFAR = 1)
        cfar_indices = [idx for idx in indices if source_labels[idx] == 1]
        if cfar_indices:
            cluster_pts = points_array[cfar_indices]
            centroid = tuple(float(x) for x in np.mean(cluster_pts, axis=0))
        else:
            cluster_pts = points_array[indices]
            centroid = tuple(float(x) for x in np.mean(cluster_pts, axis=0))
        
        has_cnn = (2 in unique_sources)
        has_adapt = (0 in unique_sources)
        has_cfar = (1 in unique_sources)
        
        if len(unique_sources) >= min_agreement:
            high_confidence_points.append(centroid)
            
            # Categorize high-confidence clusters
            if has_cnn and len(unique_sources) == 2:
                stats['cat_a_cnn_completed_pair'] += 1
            elif has_cnn and len(unique_sources) == 3:
                stats['cat_b_cnn_joined_existing'] += 1
            elif not has_cnn and len(unique_sources) == 2:
                stats['original_adapt_cfar_only'] += 1
        else:
            flagged_points.append(centroid)
            if has_cnn and len(unique_sources) == 1:
                stats['cnn_isolated_flagged'] += 1
            
    return high_confidence_points, flagged_points, stats
