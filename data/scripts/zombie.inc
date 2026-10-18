Ghostwood_EventScript_ZombieBattle::
	callnative ZombieBattle_ScriptStart
	waitstate
	lockall
	callnative ZombieBattle_Cleanup
	callnative ZombieBattle_BeginFade
	goto_if_eq VAR_RESULT, TRUE, Ghostwood_EventScript_ZombieDropLoop
	releaseall
	end
	
Ghostwood_EventScript_ZombieDropLoop::
	callnative ZombieBattle_NextDrop
	goto_if_eq VAR_RESULT, FALSE, Ghostwood_EventScript_ZombieDropDone
	additem VAR_0x8004, VAR_0x8005
	bufferitemname STR_VAR_1, VAR_0x8004
	buffernumberstring STR_VAR_2, VAR_0x8005
	goto_if_eq VAR_RESULT, FALSE, Ghostwood_EventScript_ZombieDropFull
	msgbox Ghostwood_Text_ZombieDrop, MSGBOX_AUTOCLOSE
	goto Ghostwood_EventScript_ZombieDropLoop

Ghostwood_EventScript_ZombieDropFull::
	msgbox Ghostwood_Text_ZombieDropFull, MSGBOX_AUTOCLOSE
	goto Ghostwood_EventScript_ZombieDropLoop

Ghostwood_EventScript_ZombieDropDone::
	releaseall
	end

Ghostwood_Text_ZombieDrop:
	.string "It dropped {STR_VAR_1} x{STR_VAR_2}.$"

Ghostwood_Text_ZombieDropFull:
	.string "It dropped {STR_VAR_1},\n"
	.string "but your BAG is full…$"
