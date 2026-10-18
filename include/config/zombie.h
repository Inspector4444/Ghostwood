#ifndef GUARD_CONFIG_ZOMBIE_H
#define GUARD_CONFIG_ZOMBIE_H

// ---- Ghostwood zombie hordes: tuning ----
#define ZOMBIE_SYSTEM_ENABLED       TRUE
// #define ZOMBIE_DIST_MANHATTAN // 4-dir step count / If undef, use CHEBYSHEV: 8-dir chess-like/square

// Chance (%) to add the 1st, 2nd, 3rd... mon, rolled in order; the chain stops at the first miss
#define ZOMBIE_MON_PERCENTS  { 100, 50, 33 }

#define ZOMBIE_MAX_ACTIVE           5     // per map. Must be <= ZOMBIE_LOCALID_COUNT. Object slots are shared (16 total, 4 used by OWEs)
#define ZOMBIE_LOCALID_BASE         200   // runtime-only localIds 200..(200+COUNT-1); keep clear of map-defined ids
#define ZOMBIE_LOCALID_COUNT        8

// Tiles measured as steps (|dx| + |dy|)
#define ZOMBIE_SPAWN_DIST_MIN       10 // should be a safe distance, w is 7.something tiles
#define ZOMBIE_SPAWN_DIST_MAX       16
#define ZOMBIE_DESPAWN_DIST         32
#define ZOMBIE_AGGRO_RADIUS         4
// Tiles measured as Chebyshev (max(|dx|, |dy|))
// #define ZOMBIE_SPAWN_DIST_MIN       9
// #define ZOMBIE_SPAWN_DIST_MAX       13
// #define ZOMBIE_DESPAWN_DIST         24
// #define ZOMBIE_AGGRO_RADIUS         3

#define ZOMBIE_SPAWN_INTERVAL_MIN   180   // frames between spawn attempts
#define ZOMBIE_SPAWN_INTERVAL_MAX   480
#define ZOMBIE_SPAWN_TRIES          12

#define ZOMBIE_SIGHT_RANGE          8     // straight-line sight, tiles. Must be <= ZFLOW_RADIUS
#define ZOMBIE_LOSE_INTEREST_DIST   12    // aggro drops beyond this distance

#define ZOMBIE_CHASE_FAST           TRUE // TRUE: chase at normal walk speed, FALSE: slow walk
#define ZOMBIE_MIN_MONS             1
#define ZOMBIE_MAX_MONS             3

#define ZOMBIE_FADE_FRAMES  40          // how long defeated zombies blink out
#define ZOMBIE_FLEE_BASE_PERCENT   50   // chance on the first Run attempt
#define ZOMBIE_FLEE_BONUS_PER_TRY  15   // added per failed attempt this battle
#define ZOMBIE_GRACE_FRAMES        300  // ~5 s where zombies ignore you

#endif // GUARD_CONFIG_ZOMBIE_H
