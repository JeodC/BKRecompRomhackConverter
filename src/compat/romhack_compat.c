// From src/notes.c, note_signs.c and lut_fix.c of github.com/Mr-Wiseguy/JiggiesOfTimeRecomp (CC0, c0dfbb8).

#include "modding.h"
#include "recomputils.h"
#include "recompconfig.h"
#include "structs.h"
#include "functions.h"

RECOMP_IMPORT("*", void bkrecomp_notesaving_clear_all_map_note_counts(void));
RECOMP_IMPORT("*", void bkrecomp_notesaving_set_map_static_note_count(u32 map_id, u16 static_note_count));
RECOMP_IMPORT("*", void bkrecomp_notesaving_set_map_dynamic_note_count(u32 map_id, u16 dynamic_note_count));
RECOMP_IMPORT("*", void bkrecomp_notesaving_force_disabled(bool disabled));
RECOMP_IMPORT("*", s32 bkrecomp_note_saving_active(void));

#define MAX_MAPS 256
#define MAX_HIDDEN_ACTORS 16
#define ANY 0xFFFF

#define FLAG_DISABLE_NOTE_SAVING (1 << 0)

typedef struct {
    u16 map_id;
    u16 static_count;
    u16 dynamic_count;
    u16 pad;
} MapNotes;

typedef struct {
    u16 actor_id;
    u16 model_id;
    u16 type_field;
    u16 pad;
} HiddenActor;

typedef struct {
    char magic[8];
    u32 flags;
    u32 map_count;
    u32 hidden_actor_count;
    MapNotes maps[MAX_MAPS];
    HiddenActor hidden_actors[MAX_HIDDEN_ACTORS];
} ConverterConfig;

// The converter finds this by its magic and fills it in (src/compat_config.py). Keep the layouts in sync.
__attribute__((used)) ConverterConfig converter_config = { .magic = { 'B', 'K', 'R', 'C', 'C', 'F', 'G', '1' } };

RECOMP_CALLBACK("*", recomp_on_init) void converter_on_init(void) {
    recomp_change_save_file("save");

    if (converter_config.flags & FLAG_DISABLE_NOTE_SAVING) {
        bkrecomp_notesaving_force_disabled(TRUE);
        return;
    }

    bkrecomp_notesaving_clear_all_map_note_counts();
    for (u32 i = 0; i < converter_config.map_count && i < MAX_MAPS; i++) {
        MapNotes *m = &converter_config.maps[i];
        bkrecomp_notesaving_set_map_static_note_count(m->map_id, m->static_count);
        if (m->dynamic_count) {
            bkrecomp_notesaving_set_map_dynamic_note_count(m->map_id, m->dynamic_count);
        }
    }
}

void (*hidden_actor_updates[MAX_HIDDEN_ACTORS])(Actor *);

static s32 hidden_actor_slot(u16 actor_id) {
    for (u32 i = 0; i < converter_config.hidden_actor_count && i < MAX_HIDDEN_ACTORS; i++) {
        if (converter_config.hidden_actors[i].actor_id == actor_id) {
            return i;
        }
    }
    return -1;
}

void hidden_actor_update_wrapper(Actor *actor) {
    s32 slot = hidden_actor_slot(actor->actor_info->actorId);
    HiddenActor *h = &converter_config.hidden_actors[slot];
    if (bkrecomp_note_saving_active()
        && (h->model_id == ANY || actor->actor_info->modelId == h->model_id)
        && (h->type_field == ANY || actor->actorTypeSpecificField == h->type_field)) {
        if (actor->partnerActor) {
            marker_despawn(actor->partnerActor);
        }
        marker_despawn(actor->marker);
        return;
    }

    if (hidden_actor_updates[slot]) {
        hidden_actor_updates[slot](actor);
    }
}

RECOMP_HOOK("spawnableActorList_add") void on_spawnable_actor_list_add(ActorInfo *info, Actor *(*spawn)(s32[3], s32, ActorInfo *, u32), u32 arg2) {
    s32 slot = hidden_actor_slot(info->actorId);
    if (slot >= 0 && info->update_func != hidden_actor_update_wrapper) {
        hidden_actor_updates[slot] = info->update_func;
        info->update_func = hidden_actor_update_wrapper;
    }
}

Gfx **model_render_gfx;

RECOMP_HOOK("modelRender_draw") void before_model_render_draw(Gfx **gfx, Mtx **mtx, f32 position[3], f32 rotation[3], f32 scale, f32 *arg5, BKModelBin *model_bin) {
    model_render_gfx = gfx;
}

RECOMP_HOOK_RETURN("modelRender_draw") void after_model_render_draw(void) {
    // Some custom models leave the TLUT enabled and it leaks into the next model drawn.
    if (model_render_gfx) {
        gDPSetTextureLUT((*model_render_gfx)++, G_TT_NONE);
    }
    model_render_gfx = NULL;
}
