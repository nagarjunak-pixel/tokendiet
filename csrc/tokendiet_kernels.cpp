#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <unordered_map>
#include <vector>

extern "C" {

int32_t tokendiet_salience_knapsack(
    const int32_t* token_costs,
    const int32_t* raw_scores,
    const uint64_t* line_hashes,
    const int32_t* mandatory_flags,
    int32_t n,
    int32_t budget_tokens,
    int32_t halo_radius,
    int32_t* out_selected_indices,
    int32_t* out_selected_count,
    int32_t* out_kept_tokens,
    int64_t* out_total_score
) {
    if (out_selected_count != nullptr) {
        *out_selected_count = 0;
    }
    if (out_kept_tokens != nullptr) {
        *out_kept_tokens = 0;
    }
    if (out_total_score != nullptr) {
        *out_total_score = 0;
    }
    if (n <= 0 || budget_tokens <= 0 || token_costs == nullptr || raw_scores == nullptr ||
        line_hashes == nullptr || mandatory_flags == nullptr || out_selected_indices == nullptr) {
        return 0;
    }

    const int32_t eff_halo = std::max<int32_t>(0, halo_radius);
    std::vector<uint8_t> eligible(static_cast<size_t>(n), 1);
    for (int32_t i = 0; i < n; ++i) {
        if (mandatory_flags[i] == 0 && raw_scores[i] < 800) {
            const int32_t win_start = std::max<int32_t>(0, i - 8);
            for (int32_t j = win_start; j < i; ++j) {
                if (line_hashes[j] == line_hashes[i]) {
                    eligible[static_cast<size_t>(i)] = 0;
                    break;
                }
            }
        }
    }

    std::vector<int32_t> anchors;
    anchors.reserve(static_cast<size_t>(n));
    for (int32_t i = 0; i < n; ++i) {
        if (mandatory_flags[i] != 0 || raw_scores[i] >= 800) {
            anchors.push_back(i);
        }
    }

    std::vector<int32_t> elig_indices;
    std::vector<int32_t> raw_costs;
    std::vector<int64_t> eff_scores;
    elig_indices.reserve(static_cast<size_t>(n));
    raw_costs.reserve(static_cast<size_t>(n));
    eff_scores.reserve(static_cast<size_t>(n));

    int64_t total_raw_cost = 0;
    for (int32_t i = 0; i < n; ++i) {
        if (eligible[static_cast<size_t>(i)] == 0) {
            continue;
        }
        int64_t score = static_cast<int64_t>(raw_scores[i]);
        if (eff_halo > 0) {
            for (const int32_t a : anchors) {
                const int32_t dist = std::abs(i - a);
                if (dist >= 1 && dist <= eff_halo) {
                    const int64_t propagated =
                        static_cast<int64_t>(raw_scores[a]) / (1LL + static_cast<int64_t>(dist));
                    if (propagated > score) {
                        score = propagated;
                    }
                }
            }
        }
        if (mandatory_flags[i] != 0) {
            score += 1000000LL;
        }
        const int32_t c = std::max<int32_t>(1, token_costs[i]);
        elig_indices.push_back(i);
        raw_costs.push_back(c);
        eff_scores.push_back(score);
        total_raw_cost += static_cast<int64_t>(c);
    }

    const int32_t m = static_cast<int32_t>(elig_indices.size());
    if (m == 0) {
        return 0;
    }

    int32_t selected_count = 0;
    int32_t kept_tokens = 0;
    int64_t total_score = 0;

    if (total_raw_cost <= static_cast<int64_t>(budget_tokens)) {
        for (int32_t k = 0; k < m; ++k) {
            if (eff_scores[static_cast<size_t>(k)] >= 0) {
                out_selected_indices[selected_count++] = elig_indices[static_cast<size_t>(k)];
                kept_tokens += raw_costs[static_cast<size_t>(k)];
                total_score += eff_scores[static_cast<size_t>(k)];
            }
        }
    } else {
        const int32_t scale =
            budget_tokens > 8192 ? ((budget_tokens + 8191) / 8192) : 1;
        const int32_t b_cap = budget_tokens / scale;
        std::vector<int32_t> dp_costs(static_cast<size_t>(m), 1);
        for (int32_t k = 0; k < m; ++k) {
            dp_costs[static_cast<size_t>(k)] =
                (raw_costs[static_cast<size_t>(k)] + scale - 1) / scale;
        }

        const size_t stride = static_cast<size_t>(b_cap + 1);
        std::vector<int64_t> dp_next(stride, 0);
        std::vector<int64_t> dp_curr(stride, 0);
        std::vector<uint8_t> keep(static_cast<size_t>(m) * stride, 0);

        for (int32_t k = m - 1; k >= 0; --k) {
            const int32_t w = dp_costs[static_cast<size_t>(k)];
            const int64_t v = eff_scores[static_cast<size_t>(k)];
            const size_t row_off = static_cast<size_t>(k) * stride;
            for (int32_t b = 0; b <= b_cap; ++b) {
                const int64_t skip = dp_next[static_cast<size_t>(b)];
                if (b >= w) {
                    const int64_t take = v + dp_next[static_cast<size_t>(b - w)];
                    if (take >= skip) {
                        dp_curr[static_cast<size_t>(b)] = take;
                        keep[row_off + static_cast<size_t>(b)] = 1;
                    } else {
                        dp_curr[static_cast<size_t>(b)] = skip;
                    }
                } else {
                    dp_curr[static_cast<size_t>(b)] = skip;
                }
            }
            std::swap(dp_next, dp_curr);
        }

        int32_t rem = b_cap;
        for (int32_t k = 0; k < m; ++k) {
            const size_t row_off = static_cast<size_t>(k) * stride;
            if (rem >= dp_costs[static_cast<size_t>(k)] &&
                keep[row_off + static_cast<size_t>(rem)] != 0) {
                out_selected_indices[selected_count++] = elig_indices[static_cast<size_t>(k)];
                kept_tokens += raw_costs[static_cast<size_t>(k)];
                total_score += eff_scores[static_cast<size_t>(k)];
                rem -= dp_costs[static_cast<size_t>(k)];
            }
        }
    }

    if (out_selected_count != nullptr) {
        *out_selected_count = selected_count;
    }
    if (out_kept_tokens != nullptr) {
        *out_kept_tokens = kept_tokens;
    }
    if (out_total_score != nullptr) {
        *out_total_score = total_score;
    }
    return selected_count;
}

int32_t tokendiet_dedup_blocks(
    const uint64_t* block_hashes,
    const int32_t* turn_ids,
    const int32_t* block_tokens,
    int32_t n,
    int32_t* out_ref_index,
    int32_t* out_saved_tokens
) {
    if (out_saved_tokens != nullptr) {
        *out_saved_tokens = 0;
    }
    if (n <= 0 || block_hashes == nullptr || turn_ids == nullptr ||
        block_tokens == nullptr || out_ref_index == nullptr) {
        return 0;
    }

    std::unordered_map<uint64_t, std::vector<int32_t>> by_hash;
    by_hash.reserve(static_cast<size_t>(n));

    int32_t dedup_count = 0;
    int32_t saved_tokens = 0;

    for (int32_t i = 0; i < n; ++i) {
        const uint64_t h = block_hashes[i];
        int32_t matched = -1;
        auto it = by_hash.find(h);
        if (it != by_hash.end()) {
            for (const int32_t j : it->second) {
                if (turn_ids[j] < turn_ids[i]) {
                    matched = j;
                    break;
                }
            }
        }
        out_ref_index[i] = matched;
        if (matched >= 0) {
            ++dedup_count;
            saved_tokens += std::max<int32_t>(0, block_tokens[i] - 12);
        }
        by_hash[h].push_back(i);
    }

    if (out_saved_tokens != nullptr) {
        *out_saved_tokens = saved_tokens;
    }
    return dedup_count;
}

}  // extern "C"
