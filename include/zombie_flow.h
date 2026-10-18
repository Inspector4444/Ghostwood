#ifndef GUARD_ZOMBIE_FLOW_H
#define GUARD_ZOMBIE_FLOW_H

// Local BFS "flow field" around a target tile. Zombies read the next step from it.
#define ZFLOW_RADIUS 10
#define ZFLOW_SIZE   (ZFLOW_RADIUS * 2 + 1)

typedef bool8 (*ZombieFlowPassableFunc)(s16 x, s16 y);

// Rebuild the field centered on (targetX, targetY), absolute map coords.
void ZombieFlow_Build(s16 targetX, s16 targetY, ZombieFlowPassableFunc isPassable);
// Direction (DIR_SOUTH/NORTH/WEST/EAST) of the best step from (x, y), or DIR_NONE
// if outside the field / no way forward.
u8 ZombieFlow_GetDirection(s16 x, s16 y);
// Neighbour steps that are NOT farther from the target than (x, y), best first.
// rotate breaks ties differently per zombie so a crowd spreads out.
u32 ZombieFlow_GetDirections(s16 x, s16 y, u8 rotate, u8 outDirs[4]);
bool8 ZombieFlow_IsInside(s16 x, s16 y);
void ZombieFlow_Invalidate(void);

#endif // GUARD_ZOMBIE_FLOW_H
