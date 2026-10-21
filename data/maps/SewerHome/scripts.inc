SewerHome_MapScripts::
	.byte 0

SewerHome_EventScript_Sketchy_Guy::
	lock
	faceplayer
	msgbox Sewer_Home_Text_WeaponsDealer, MSGBOX_DEFAULT
	release
	end

Sewer_Home_Text_WeaponsDealer:
	.string "Whatcha lookin' at!?\n"
	.string "I sell weapons, tools, the like.\p"
	.string "I'm not interested in selling\n"
	.string "to you!$"
	