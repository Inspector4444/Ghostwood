#include "global.h"
#include "zombie_flow.h"
#include "fieldmap.h"
#include "metatile_behavior.h"

#define COST_BLOCKED 0xFE
#define COST_NONE    0xFF

static EWRAM_DATA u8 sCost[ZFLOW_SIZE][ZFLOW_SIZE] = {0};
static EWRAM_DATA u8 sHopDir[ZFLOW_SIZE][ZFLOW_SIZE] = {0}; // DIR_NONE unless best route from here is a ledge hop
static EWRAM_DATA s16 sOriginX = 0; // map coords of sCost[0][0]
static EWRAM_DATA s16 sOriginY = 0;
static EWRAM_DATA bool8 sValid = FALSE;

static const s8 sDx[4] = { 0,  0, -1, 1};
static const s8 sDy[4] = { 1, -1,  0, 0};
static const u8 sDirs[4] = {DIR_SOUTH, DIR_NORTH, DIR_WEST, DIR_EAST};

bool8 ZombieFlow_IsInside(s16 x, s16 y)
{
    s16 lx = x - sOriginX, ly = y - sOriginY;
    return sValid && lx >= 0 && ly >= 0 && lx < ZFLOW_SIZE && ly < ZFLOW_SIZE;
}

void ZombieFlow_Invalidate(void)
{
    sValid = FALSE;
}

static u8 GetLedgeDirAt(s16 x, s16 y)
{
    u8 b = MapGridGetMetatileBehaviorAt(x, y);

    if (MetatileBehavior_IsJumpSouth(b)) return DIR_SOUTH;
    if (MetatileBehavior_IsJumpNorth(b)) return DIR_NORTH;
    if (MetatileBehavior_IsJumpWest(b))  return DIR_WEST;
    if (MetatileBehavior_IsJumpEast(b))  return DIR_EAST;
    return DIR_NONE;
}

void ZombieFlow_Build(s16 targetX, s16 targetY, ZombieFlowPassableFunc isPassable)
{
    static EWRAM_DATA u16 sQueue[ZFLOW_SIZE * ZFLOW_SIZE];
    u32 head = 0, tail = 0, x, y, i;

    sOriginX = targetX - ZFLOW_RADIUS;
    sOriginY = targetY - ZFLOW_RADIUS;
    for (y = 0; y < ZFLOW_SIZE; y++)
    {
        for (x = 0; x < ZFLOW_SIZE; x++)
        {
            sCost[y][x] = COST_NONE;
            sHopDir[y][x] = DIR_NONE;
        }
    }

    sCost[ZFLOW_RADIUS][ZFLOW_RADIUS] = 0;
    sQueue[tail++] = (ZFLOW_RADIUS << 8) | ZFLOW_RADIUS;
    sValid = TRUE;

    while (head < tail)
    {
        u16 cur = sQueue[head++];
        s32 cx = cur & 0xFF, cy = cur >> 8;
        u8 next = sCost[cy][cx] + 1;

        if (next >= COST_BLOCKED)
            continue;
        for (i = 0; i < 4; i++)
        {
            s32 nx = cx + sDx[i], ny = cy + sDy[i];
            s32 px = nx + sDx[i], py = ny + sDy[i];   // tile beyond (nx,ny), a possible hop start
            s16 wx = sOriginX + nx, wy = sOriginY + ny;
            u8 ledge;

            if (nx < 0 || ny < 0 || nx >= ZFLOW_SIZE || ny >= ZFLOW_SIZE)
                continue;
            if (sCost[ny][nx] != COST_NONE)
                continue;
            ledge = GetLedgeDirAt(wx, wy);
            if (ledge != DIR_NONE || !isPassable(wx, wy))
            {
                sCost[ny][nx] = COST_BLOCKED;
                // a ledge we can hop toward the player: the tile behind it is a hop start
                if (ledge != DIR_NONE && ledge == sDirs[i ^ 1]
                 && next + 1 < COST_BLOCKED
                 && px >= 0 && py >= 0 && px < ZFLOW_SIZE && py < ZFLOW_SIZE
                 && sCost[py][px] == COST_NONE
                 && isPassable(sOriginX + px, sOriginY + py))
                {
                    sCost[py][px] = next + 1;
                    sHopDir[py][px] = ledge;
                    sQueue[tail++] = (py << 8) | px;
                }
                continue;
            }
            sCost[ny][nx] = next;
            sQueue[tail++] = (ny << 8) | nx;
        }
    }
}

u8 ZombieFlow_GetDirection(s16 x, s16 y)
{
    s32 lx = x - sOriginX, ly = y - sOriginY, i;
    u8 best = DIR_NONE, bestCost = COST_BLOCKED;
    u8 here;

    if (!ZombieFlow_IsInside(x, y))
        return DIR_NONE;
    here = sCost[ly][lx];
    if (here == 0)
        return DIR_NONE;
    for (i = 0; i < 4; i++)
    {
        s32 nx = lx + sDx[i], ny = ly + sDy[i];
        if (nx < 0 || ny < 0 || nx >= ZFLOW_SIZE || ny >= ZFLOW_SIZE)
            continue;
        if (sCost[ny][nx] < bestCost && sCost[ny][nx] < here)
        {
            bestCost = sCost[ny][nx];
            best = sDirs[i];
        }
    }
    if (sHopDir[ly][lx] != DIR_NONE && here >= 2
     && (best == DIR_NONE || bestCost > here - 2))
        best = sHopDir[ly][lx];
    return best;
}

u32 ZombieFlow_GetDirections(s16 x, s16 y, u8 rotate, u8 outDirs[4])
{
    u8 costs[4];
    u32 n = 0, k, j;
    s32 lx = x - sOriginX, ly = y - sOriginY;
    u8 here;

    if (!ZombieFlow_IsInside(x, y))
        return 0;
    here = sCost[ly][lx];
    for (k = 0; k < 4; k++)
    {
        u32 i = (k + rotate) & 3;
        s32 nx = lx + sDx[i], ny = ly + sDy[i];
        u8 c;

        if (nx < 0 || ny < 0 || nx >= ZFLOW_SIZE || ny >= ZFLOW_SIZE)
            continue;
        c = sCost[ny][nx];
        if (c >= COST_BLOCKED || c > here) // blocked, unknown, or farther away
            continue;
        // stable insertion sort by cost
        for (j = n; j > 0 && costs[j - 1] > c; j--)
        {
            costs[j] = costs[j - 1];
            outDirs[j] = outDirs[j - 1];
        }
        costs[j] = c;
        outDirs[j] = sDirs[i];
        n++;
    }
    if (sHopDir[ly][lx] != DIR_NONE && here >= 2)
    {
        u8 c = here - 2;

        for (j = n; j > 0 && costs[j - 1] > c; j--)
        {
            costs[j] = costs[j - 1];
            outDirs[j] = outDirs[j - 1];
        }
        costs[j] = c;
        outDirs[j] = sHopDir[ly][lx];
        n++;
    }
    return n;
}