from __future__ import annotations

import math
import numpy as np

from atabey.types import Detection, LineageGraph

def _angle_between(v1: np.ndarray, v2: np.ndarray) -> float:
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    cos_t = np.dot(v1, v2) / (n1 * n2)
    return float(math.degrees(math.acos(np.clip(cos_t, -1.0, 1.0))))

def prune_invalid_divisions(graph: LineageGraph, debug: bool = False) -> None:
    """Apply multi-frame division firewall to prune false positive divisions.
    
    Must be called after the graph is fully constructed (post-streaming).
    Identifies 1-to-2 branches, tracks them forward up to 3 frames, and rejects
    if they do not exhibit true anaphase kinematics (directional consistency + initial velocity).
    If rejected, the edge to the orphan daughter is dropped and the primary daughter's edge
    is converted to a standard continuation.
    """
    
    detections = list(graph.detections)
    edges = list(graph.edges)
    
    by_id: dict[str, Detection] = {d.node_id: d for d in detections}
    outgoing_by_source: dict[str, list[str]] = {}
    for edge in edges:
        outgoing_by_source.setdefault(edge.source_id, []).append(edge.target_id)
        
    parents = [src for src, targets in outgoing_by_source.items() if len(targets) == 2]
    
    edges_to_remove = []
    edges_to_modify = []
    
    for parent_id in parents:
        p_node = by_id[parent_id]
        targets = outgoing_by_source[parent_id]
        
        # Identify primary and orphan. Primary is the one closer to the parent.
        t1_node = by_id[targets[0]]
        t2_node = by_id[targets[1]]
        
        d1 = np.linalg.norm(np.array(t1_node.position_um) - np.array(p_node.position_um))
        d2 = np.linalg.norm(np.array(t2_node.position_um) - np.array(p_node.position_um))
        
        if d1 <= d2:
            primary_id = targets[0]
            orphan_id = targets[1]
        else:
            primary_id = targets[1]
            orphan_id = targets[0]
            
        def get_descendant_at(node_id: str, target_t: int) -> Detection | None:
            current = by_id[node_id]
            while current.t < target_t:
                out = outgoing_by_source.get(current.node_id, [])
                if not out:
                    return None
                current = by_id[out[0]]
            return current
            
        d1_nodes = [by_id[primary_id]]
        d2_nodes = [by_id[orphan_id]]
        
        # Track up to T+3
        for offset in [2, 3]:
            if d1_nodes[-1] is None or d2_nodes[-1] is None:
                d1_nodes.append(None)
                d2_nodes.append(None)
                continue
            d1_nodes.append(get_descendant_at(d1_nodes[-1].node_id, p_node.t + offset))
            d2_nodes.append(get_descendant_at(d2_nodes[-1].node_id, p_node.t + offset))
            
        axes = []
        seps = []
        for n1, n2 in zip(d1_nodes, d2_nodes):
            if n1 and n2:
                v = np.array(n1.position_um) - np.array(n2.position_um)
                axes.append(v)
                seps.append(float(np.linalg.norm(v)))
                
        reject = False
        rejection_reason = ""
        
        if len(axes) >= 3:
            # We have T+1, T+2, T+3
            angles = []
            for i in range(len(axes)-1):
                ang = _angle_between(axes[i], axes[i+1])
                ang = min(ang, 180.0 - ang)
                angles.append(ang)
                
            max_drift = max(angles)
            v_sep_1 = seps[1] - seps[0]
            
            if max_drift >= 15.0 or v_sep_1 <= 1.0:
                reject = True
                rejection_reason = f"Drift={max_drift:.1f}, v_sep_1={v_sep_1:.1f}"
        else:
            # Fallback to strict T0 geometry
            v1 = np.array(by_id[primary_id].position_um) - np.array(p_node.position_um)
            v2 = np.array(by_id[orphan_id].position_um) - np.array(p_node.position_um)
            n1 = float(np.linalg.norm(v1))
            n2 = float(np.linalg.norm(v2))
            ang = _angle_between(v1, v2)
            
            if n1 < 1e-6 or n2 < 1e-6:
                reject = True
                rejection_reason = "Fallback: Zero vector"
            else:
                ratio = max(n1, n2) / min(n1, n2)
                if ang <= 90.0 or ratio >= 2.0:
                    reject = True
                    rejection_reason = f"Fallback: ang={ang:.1f}, ratio={ratio:.1f}"
                    
        if reject:
            if debug:
                print(f"[FIREWALL] Rejected {parent_id[:6]} -> {primary_id[:6]} & {orphan_id[:6]}: {rejection_reason}")
            edges_to_remove.append((parent_id, orphan_id))
            edges_to_modify.append((parent_id, primary_id, "spatial_nearest_neighbor"))
            
    # Apply modifications
    if debug and edges_to_remove:
        print(f"[FIREWALL] Pruning {len(edges_to_remove)} invalid divisions.")
        
    for u, v in edges_to_remove:
        # Find and remove the edge object
        for edge in list(graph.edges):
            if edge.source_id == u and edge.target_id == v:
                graph.remove_edge(edge)
                
    for u, v, new_rel in edges_to_modify:
        for edge in list(graph.edges):
            if edge.source_id == u and edge.target_id == v:
                import dataclasses
                graph.remove_edge(edge)
                new_edge = dataclasses.replace(edge, relation=new_rel)
                graph.add_edge(new_edge)
                break
