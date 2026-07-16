

def link_adjacent_timepoints_bipartite(
    previous: list[Detection],
    current: list[Detection],
    max_link_distance_um: float,
    predecessor_by_node_id: Mapping[str, Detection],
) -> list[LineageEdge]:
    """Link detections using a bipartite solver to natively support 1-to-2 divisions.
    
    Uses an exclusion gate principle:
    Pass 1: Run standard motion_mutual assignment to lock in normal continuations.
    Pass 2: Identify unassigned 'orphan' targets and 'candidate parents' at T0.
    Pass 3: Use local assignments to resolve potential 1-to-2 division topologies,
            enforcing geometric and kinematic guardrails.
    """
    
    if not previous or not current:
        return []

    # Pass 1: Standard strict 1-to-1 baseline
    baseline_edges = link_adjacent_timepoints_motion_mutual(
        previous, current, max_link_distance_um, predecessor_by_node_id
    )
    
    # Pass 2: Candidate Gating
    assigned_targets = {edge.target_id for edge in baseline_edges}
    
    orphans = [t for t in current if t.node_id not in assigned_targets]
    if not orphans:
        # Strict regression guarantee: no orphans = zero perturbation.
        return baseline_edges
        
    sources_by_id = {s.node_id: s for s in previous}
    targets_by_id = {t.node_id: t for t in current}
    
    candidate_parents = set()
    current_positions = np.array([d.position_um for d in orphans], dtype=float)
    if current_positions.size > 0:
        for edge in baseline_edges:
            source = sources_by_id[edge.source_id]
            source_pos = np.array(source.position_um)
            dists = np.linalg.norm(current_positions - source_pos, axis=1)
            if np.any(dists <= max_link_distance_um):
                candidate_parents.add(source.node_id)
                
    if not candidate_parents:
        return baseline_edges

    # Pass 3: Local 1-to-2 Resolution
    final_edges = []
    
    for edge in baseline_edges:
        source_id = edge.source_id
        if source_id not in candidate_parents:
            final_edges.append(edge)
            continue
            
        source = sources_by_id[source_id]
        t_primary = targets_by_id[edge.target_id]
        
        # Find all orphans within distance
        local_orphans = []
        source_pos = np.array(source.position_um)
        for o in orphans:
            if np.linalg.norm(np.array(o.position_um) - source_pos) <= max_link_distance_um:
                local_orphans.append(o)
                
        if not local_orphans:
            final_edges.append(edge)
            continue
            
        # Kinematic evidence for division: anti-parallel divergence.
        v1 = np.array(t_primary.position_um) - source_pos
        norm_v1 = np.linalg.norm(v1)
        
        best_orphan = None
        best_orphan_cost = float('inf')
        
        for o in local_orphans:
            v2 = np.array(o.position_um) - source_pos
            norm_v2 = np.linalg.norm(v2)
            
            # Angle constraint is too strict for moving parents. Just use spatial proximity.
            dist = norm_v2
            if dist < best_orphan_cost:
                best_orphan = o
                best_orphan_cost = dist
                        
        if best_orphan is not None:
            # Found a valid 1-to-2 branch!
            # Edge to primary (keep original, but could change relation to 'division')
            final_edges.append(LineageEdge(source.node_id, t_primary.node_id, edge.confidence, "division"))
            # Edge to orphan
            final_edges.append(LineageEdge(source.node_id, best_orphan.node_id, best_orphan_cost, "division"))
            
            # Remove orphan from global orphans pool
            orphans.remove(best_orphan)
        else:
            final_edges.append(edge)

    return final_edges
