from __future__ import annotations
import streamlit as st
import json
import importlib
import sys
import time
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple

import models
importlib.reload(models)
import solver
importlib.reload(solver)
import sample_data
importlib.reload(sample_data)
import exporters
importlib.reload(exporters)
import importers
importlib.reload(importers)
import support_solver
importlib.reload(support_solver)
import support_ui
importlib.reload(support_ui)
import pdf_export
importlib.reload(pdf_export)
from support_ui import (
    render_support_management_tab,
    render_support_solver_section,
    render_support_timetables_view
)
import schedule_validator
importlib.reload(schedule_validator)
import manual_editor_engine
importlib.reload(manual_editor_engine)
import schedule_importer
importlib.reload(schedule_importer)
import manual_editor_ui
importlib.reload(manual_editor_ui)
from manual_editor_ui import render_manual_editor_and_import_panel

from models import (
    SchoolConfig, Teacher, SchoolClass, Subject, Classroom,
    TeachingAssignment, TimetableProblem, DAYS_OF_WEEK, OptimizationCriteria, ParallelGroup,
    StudentDVA, SupportAssignment, EnhancementAssignment, DISCIPLINARY_AREAS
)
from sample_data import get_sample_problem, get_empty_problem
from solver import TimetableSolver, TimetableResult, get_room_bottlenecks, diagnose_problem_feasibility
from exporters import generate_excel_timetable, generate_excel_tabellone_combo
from pdf_export import (
    generate_classes_pdf, generate_teachers_pdf, generate_rooms_pdf,
    generate_support_teachers_pdf, generate_classes_with_support_pdf
)
from importers import (
    generate_csv_template, generate_excel_template, 
    parse_csv_timetable, parse_excel_timetable,
    generate_teacher_desiderata_form, merge_teacher_desiderata_file,
    generate_unified_school_excel, parse_unified_school_excel
)

def create_safe_teacher(
    id: str,
    name: str,
    cdc: str = "",
    is_part_time: bool = False,
    contract_hours: Optional[int] = None,
    max_working_days: Optional[int] = None,
    free_days: Optional[List[str]] = None,
    free_day_1: Optional[str] = None,
    free_day_2: Optional[str] = None,
    preferred_areas: Optional[List[str]] = None,
    unavailable_slots: Optional[List[List[int]]] = None,
    required_slots: Optional[List[List[int]]] = None,
    prefer_late_entry: bool = False,
    prefer_early_exit: bool = False,
    late_entry_days: Optional[List[str]] = None,
    early_exit_days: Optional[List[str]] = None,
    soft_avoid_slots: Optional[List[List[int]]] = None,
    min_daily_hours: int = 2,
    max_daily_hours: int = 5,
    max_consecutive_hours: int = 4,
    max_gap_hours: int = 2,
    prefer_compact_schedule: bool = True,
    **kwargs
) -> Teacher:
    """Costruttore resiliente compatibile con qualsiasi versione in memoria di Teacher."""
    t = Teacher(id=id, name=name)
    t.cdc = cdc
    t.is_part_time = is_part_time
    t.contract_hours = contract_hours
    t.max_working_days = max_working_days
    t.preferred_areas = preferred_areas or []
    
    # Normalizza lista giorni liberi
    f_list = [d for d in (free_days or []) if d and d != "Nessuno"]
    if not f_list:
        if free_day_1 and free_day_1 != "Nessuno": f_list.append(free_day_1)
        if free_day_2 and free_day_2 != "Nessuno": f_list.append(free_day_2)

    t.free_days = f_list
    t.free_day_1 = f_list[0] if len(f_list) > 0 else None
    t.free_day_2 = f_list[1] if len(f_list) > 1 else None
    
    t.unavailable_slots = unavailable_slots or []
    t.required_slots = required_slots or []
    t.prefer_late_entry = prefer_late_entry
    t.prefer_early_exit = prefer_early_exit
    t.late_entry_days = late_entry_days or []
    t.early_exit_days = early_exit_days or []
    t.soft_avoid_slots = soft_avoid_slots or []
    t.min_daily_hours = min_daily_hours
    t.max_daily_hours = max_daily_hours
    t.max_consecutive_hours = max_consecutive_hours
    t.max_gap_hours = max_gap_hours
    t.prefer_compact_schedule = prefer_compact_schedule
    for k, v in kwargs.items():
        setattr(t, k, v)
    return t

from schedule_renderer import render_html_schedule_table

def get_teacher_subjects_display(t: Teacher, problem: TimetableProblem) -> str:
    t_assigns = [a for a in problem.assignments if a.teacher_id == t.id or t.id in getattr(a, "co_teacher_ids", [])]
    s_ids = list(dict.fromkeys(a.subject_id for a in t_assigns))
    if s_ids:
        names = [problem.subjects[s].name for s in s_ids if s in problem.subjects]
        if names:
            return ", ".join(names)
    cdc_val = getattr(t, "cdc", "")
    mapping = {
        "A-22": "Italiano, Storia, Geografia",
        "A-28": "Matematica e Scienze",
        "A-24": "Inglese / Spagnolo",
        "A-60": "Tecnologia",
        "A-30": "Musica",
        "A-56": "Strumento Musicale",
        "A-01": "Arte e Immagine",
        "A-48": "Scienze Motorie",
        "Religione": "Religione Cattolica",
        "ADMM": "Sostegno",
        "Sostegno": "Sostegno"
    }
    for k, v in mapping.items():
        if k in cdc_val:
            return v
    if "sostegno" in t.name.lower() or "sostegno" in cdc_val.lower() or "admm" in cdc_val.lower():
        return "Sostegno"
    return "Docente"

def render_subject_coupling_panel(problem: TimetableProblem, key_prefix: str = "main"):
    """Pannello interattivo per scegliere quali materie accoppiare forzatamente a blocchi da 2 ore e quali no."""
    st.markdown("#### 🔗 Scelta Accoppiamento Forzato Materie (Blocchi da 2 Ore Consecutive)")
    st.caption("Scegli quali discipline accoppiare forzatamente (es. 2h di fila nello stesso giorno per **Arte**, **Tecnologia**, **Motoria** o blocchi di **Italiano** / **Matematica**) e quali mantenere ad **ore singole separate** (es. 1h al giorno per **Musica**, **Scienze**, **Lingue**).")
    
    if not problem.subjects:
        st.info("Nessuna materia configurata.")
        return

    # Inizializza preferenze di default se vuote (Default: solo Scienze Motorie e Italiano)
    if not hasattr(problem.config, "subject_block_preferences") or not problem.config.subject_block_preferences:
        problem.config.subject_block_preferences = {
            "ita": True, "mot": True,
            "art": False, "tec": False, "mus": False, "spa": False, "mat": False,
            "ing": False, "sci": False, "sto": False, "geo": False, "rel": False
        }

    preset_state_key = f"{key_prefix}_active_coupling_preset"
    if preset_state_key not in st.session_state:
        st.session_state[preset_state_key] = "custom"

    cur_p = st.session_state[preset_state_key]

    def sync_all_assignments_from_preferences():
        # 1. Incrementa la versione globale per forzare il refresh immediato di tutti i checkbox nei Tab 2, 3 e 4
        st.session_state["block_prefs_version"] = st.session_state.get("block_prefs_version", 0) + 1

        # 2. Sincronizza tutte le cattedre registrate nell'intero database
        for a in problem.assignments:
            should_c = problem.config.subject_block_preferences.get(a.subject_id, False)
            if should_c and a.hours_per_week >= 2:
                a.force_double_hours = True
                a.max_daily_hours = 2 if a.hours_per_week <= 5 else 4
            else:
                a.force_double_hours = False
                a.max_daily_hours = 1 if a.hours_per_week in [2, 3] else 2

        # 3. Sincronizza anche il modulo temporaneo docente attualmente aperto in modifica
        if "teacher_temp_assigns" in st.session_state and st.session_state.teacher_temp_assigns:
            for item in st.session_state.teacher_temp_assigns:
                s_id = item.get("subject_id")
                h_pw = item.get("hours_per_week", 2)
                should_c = problem.config.subject_block_preferences.get(s_id, False)
                item["force_double_hours"] = bool(should_c and h_pw >= 2)
                item["max_daily_hours"] = 2 if item["force_double_hours"] else (1 if h_pw in [2, 3] else 2)

    def apply_preset(preset_type: str):
        st.session_state[preset_state_key] = preset_type
        for s_id in problem.subjects:
            val = False
            if preset_type == "labs":
                val = (s_id in ["art", "tec", "mot", "mus"])
            elif preset_type == "all":
                val = True
            elif preset_type == "std":
                val = (s_id in ["ita", "mat", "art", "tec", "mot", "mus", "spa"])
            elif preset_type == "none":
                val = False
            problem.config.subject_block_preferences[s_id] = val
            w_k = f"{key_prefix}_sub_block_{s_id}"
            st.session_state[w_k] = val
        sync_all_assignments_from_preferences()
        st.session_state.result = None
        st.rerun()

    def on_checkbox_toggle(sub_id: str, widget_key: str):
        val = bool(st.session_state[widget_key])
        problem.config.subject_block_preferences[sub_id] = val
        st.session_state[preset_state_key] = "custom"
        sync_all_assignments_from_preferences()
        st.session_state.result = None

    # Preset Rapidi con evidenziazione del preset ATTIVO (Pulsante Blu quando attivo)
    st.markdown("##### ⚡ Preset Rapidi di Accoppiamento")
    c_p1, c_p2, c_p3, c_p4 = st.columns(4)
    with c_p1:
        is_active = (cur_p == "labs")
        label = "🎨 Solo Laboratori (Arte, Tec, Mot, Mus)"
        if st.button(f"{'✅ ' if is_active else ''}{label}", key=f"{key_prefix}_preset_labs", type="primary" if is_active else "secondary", use_container_width=True):
            apply_preset("labs")
    with c_p2:
        is_active = (cur_p == "all")
        label = "🏫 Massimo Accorpamento (Tutte ≥ 2h)"
        if st.button(f"{'✅ ' if is_active else ''}{label}", key=f"{key_prefix}_preset_all", type="primary" if is_active else "secondary", use_container_width=True):
            apply_preset("all")
    with c_p3:
        is_active = (cur_p == "std")
        label = "📖 Standard (Lettere, Mat, Lingua + Lab)"
        if st.button(f"{'✅ ' if is_active else ''}{label}", key=f"{key_prefix}_preset_std", type="primary" if is_active else "secondary", use_container_width=True):
            apply_preset("std")
    with c_p4:
        is_active = (cur_p == "none")
        label = "🔓 Tutte Ore Singole Separate"
        if st.button(f"{'✅ ' if is_active else ''}{label}", key=f"{key_prefix}_preset_none", type="primary" if is_active else "secondary", use_container_width=True):
            apply_preset("none")

    # Griglia di selezione per materia
    all_subs = list(problem.subjects.values())
    cols_count = 3
    sub_cols = st.columns(cols_count)
    
    bp_v = st.session_state.get("block_prefs_version", 0)
    for idx, s in enumerate(all_subs):
        col_idx = idx % cols_count
        with sub_cols[col_idx]:
            w_key = f"{key_prefix}_sub_block_{s.id}_{bp_v}"
            if s.id not in problem.config.subject_block_preferences:
                problem.config.subject_block_preferences[s.id] = (s.id in ["art", "tec", "mot", "mus", "spa", "ita", "mat"])
            current_pref = problem.config.subject_block_preferences[s.id]
            if w_key not in st.session_state:
                st.session_state[w_key] = current_pref

            st.checkbox(
                f"**{s.name}**",
                key=w_key,
                on_change=on_checkbox_toggle,
                args=(s.id, w_key),
                help=f"Se spuntato, le ore di {s.name} vengono forzate a blocchi di 2 ore consecutive nello stesso giorno."
            )

    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    st.markdown("##### 📝 Gestione Speciale Disciplina: Italiano / Lettere (Tema & Laboratorio di Scrittura)")
    
    col_ita_blk1, col_ita_blk2 = st.columns(2)
    
    # 1. Spunta Forzata a livello di Istituto (1 blocco da 3 ore consecutive per tutte le classi)
    force_ita_key = f"{key_prefix}_force_triple_ita"
    cur_force_triple = getattr(problem.config, "force_triple_hours_italian", False)
    if force_ita_key not in st.session_state:
        st.session_state[force_ita_key] = cur_force_triple
        
    def on_force_triple_toggle():
        val = st.session_state[force_ita_key]
        problem.config.force_triple_hours_italian = val
        if val:
            problem.config.allow_triple_hours_italian = True
            st.session_state[f"{key_prefix}_allow_triple_ita"] = True
        # Aggiorna tutte le cattedre di Italiano nell'organico
        for a in problem.assignments:
            if a.subject_id == "ita" or "italian" in a.subject_id.lower():
                a.force_triple_hours = val
                a.max_daily_hours = 3 if val else 2
        st.session_state.result = None
        st.session_state["block_prefs_version"] = st.session_state.get("block_prefs_version", 0) + 1

    with col_ita_blk1:
        st.checkbox(
            "🔒 **FORZA 1 Blocco da 3 Ore Consecutive di Italiano** *(Tema di Lettere)*",
            key=force_ita_key,
            on_change=on_force_triple_toggle,
            help="Se spuntato a livello di istituto, impone tassativamente a TUTTE le classi e a TUTTI i docenti di Lettere esattamente 1 giornata con 3 ore consecutive per il tema in classe (e max 2h negli altri giorni)."
        )

    # 2. Consenti fino a 3 ore (senza obbligo)
    allow_ita_key = f"{key_prefix}_allow_triple_ita"
    cur_allow_triple = getattr(problem.config, "allow_triple_hours_italian", False) or cur_force_triple
    if allow_ita_key not in st.session_state:
        st.session_state[allow_ita_key] = cur_allow_triple
        
    def on_allow_triple_toggle():
        val = st.session_state[allow_ita_key]
        problem.config.allow_triple_hours_italian = val
        if not val and problem.config.force_triple_hours_italian:
            problem.config.force_triple_hours_italian = False
            st.session_state[force_ita_key] = False
        st.session_state.result = None

    with col_ita_blk2:
        is_dis_allow = st.session_state.get(force_ita_key, False)
        st.checkbox(
            "🔓 **Consenti fino a 3 ore di Italiano** *(Opzionale/Flessibile)*",
            key=allow_ita_key,
            disabled=is_dis_allow,
            on_change=on_allow_triple_toggle,
            help="Permette al solutore di accorpare fino a 3 ore di Italiano se utile, senza renderlo un vincolo forzato su tutte le classi."
        )

    st.markdown("<hr style='margin: 10px 0;'>", unsafe_allow_html=True)
    st.markdown("##### 👤 Coppie Forzate per Docente (Blocchi da 2 Ore per Insegnante)")
    st.caption("Seleziona un singolo docente dal menu a tendina per forzare a 2 ore consecutive le sue cattedre (anche se la materia è impostata a ore singole a livello di istituto).")

    if not problem.teachers:
        st.info("Nessun docente registrato nel database.")
    else:
        sorted_teachers = sorted(problem.teachers.values(), key=lambda t: t.name)
        t_options = [t.id for t in sorted_teachers]
        
        sel_t_id = st.selectbox(
            "Seleziona Docente per gestire i Blocchi da 2 Ore:",
            options=t_options,
            format_func=lambda tid: f"👤 {problem.teachers[tid].name} ({get_teacher_subjects_display(problem.teachers[tid], problem)})",
            key=f"{key_prefix}_sel_teacher_coupling"
        )
        
        if sel_t_id:
            t_obj = problem.teachers[sel_t_id]
            t_assigns = [a for a in problem.assignments if a.teacher_id == sel_t_id or sel_t_id in getattr(a, "co_teacher_ids", [])]
            
            if not t_assigns:
                st.info(f"Nessuna cattedra assegnata a {t_obj.name}.")
            else:
                c_tc1, c_tc2 = st.columns([1.5, 2.5])
                with c_tc1:
                    st.markdown(f"**Cattedre di {t_obj.name}** *(Totale: {sum(a.hours_per_week for a in t_assigns)}h)*")
                    # Bottone rapido per forzare tutte le cattedre di questo docente a 2h
                    all_forced = all(a.force_double_hours for a in t_assigns if a.hours_per_week >= 2)
                    btn_label = "🔓 Disattiva Blocchi 2h per Tutto il Docente" if all_forced else "⚡ Forza Blocchi 2h su Tutte le sue Cattedre"
                    if st.button(btn_label, key=f"{key_prefix}_btn_toggle_all_{sel_t_id}", use_container_width=True):
                        new_val = not all_forced
                        for a in t_assigns:
                            if a.hours_per_week >= 2:
                                a.force_double_hours = new_val
                                a.max_daily_hours = 2 if new_val else (1 if a.hours_per_week in [2, 3] else 2)
                        st.session_state["block_prefs_version"] = st.session_state.get("block_prefs_version", 0) + 1
                        st.session_state.result = None
                        st.rerun()

                with c_tc2:
                    t_bp_v = st.session_state.get("block_prefs_version", 0)
                    for a_item in t_assigns:
                        s_name = problem.subjects[a_item.subject_id].name if a_item.subject_id in problem.subjects else a_item.subject_id
                        c_name = problem.classes[a_item.class_id].name if a_item.class_id in problem.classes else a_item.class_id
                        w_key_a = f"{key_prefix}_t_assign_dbl_{a_item.id}_{t_bp_v}"
                        
                        can_dbl = (a_item.hours_per_week >= 2)
                        if w_key_a not in st.session_state:
                            st.session_state[w_key_a] = bool(a_item.force_double_hours)

                        def on_teacher_assign_toggle(assign_obj=a_item, wkey=w_key_a):
                            v_flag = bool(st.session_state[wkey])
                            assign_obj.force_double_hours = v_flag
                            assign_obj.max_daily_hours = 2 if v_flag else (1 if assign_obj.hours_per_week in [2, 3] else 2)
                            st.session_state.result = None

                        st.checkbox(
                            f"**Classe {c_name}** - {s_name} ({a_item.hours_per_week}h/settimana)",
                            key=w_key_a,
                            value=bool(a_item.force_double_hours),
                            disabled=(not can_dbl),
                            on_change=on_teacher_assign_toggle,
                            help=f"Forza il docente a svolgere le ore di {s_name} in classe {c_name} a blocchi di 2 ore consecutive."
                        )

def render_parallel_classes_panel(problem: TimetableProblem, key_prefix: str = "main"):
    """Pannello interattivo per la configurazione delle Classi Aperte & Parallelismi Didattici."""
    st.markdown("#### 👥 Classi Aperte & Parallelismi Didattici (Lezioni in Contemporanea)")
    st.caption("Configura lezioni sincronizzate nello stesso identico momento per 2 o più classi (es. accoppiamento a coppie per Scienze Motorie/Palestra, parallelismo su tutte le classi prime per Italiano a 2h, gruppi di livello o laboratori aperti).")
    
    if not hasattr(problem.config, "parallel_groups") or problem.config.parallel_groups is None:
        problem.config.parallel_groups = []
        
    p_groups = problem.config.parallel_groups
    
    # -------------------------------------------------------------
    # 1. GENERATORI RAPIDI (PRESET CON 1 CLICK)
    # -------------------------------------------------------------
    with st.expander("⚡ Creazione Automatica con Preset Rapidi (Palestra a Coppie / Parallelismo per Anno)", expanded=(len(p_groups) == 0)):
        p_col1, p_col2 = st.columns(2)
        
        with p_col1:
            st.markdown("##### 🏃‍♂️ Preset 1: Accoppia Sezioni per Scienze Motorie / Palestra")
            st.caption("Accoppia automaticamente le classi a due a due per fare ginnastica insieme nella stessa ora (es. 1A+1D, 1B+1E, 1C+1F).")
            
            target_grade_mot = st.selectbox(
                "Quale anno di corso vuoi accoppiare?",
                options=["Tutti gli Anni (Prime, Seconde e Terze)", "Solo Classi Terze (3ª)", "Solo Classi Seconde (2ª)", "Solo Classi Prime (1ª)"],
                key=f"{key_prefix}_preset_mot_grade"
            )
            
            mot_room_opts = ["Nessuno / Aule Separate"] + [r_id for r_id, r in problem.rooms.items() if "mot" in r.subject_ids or r.is_special_lab or "palestra" in r.id.lower() or "palestra" in r.name.lower()]
            sel_mot_room = st.selectbox(
                "Palestra / Spazio Condiviso:",
                options=mot_room_opts,
                format_func=lambda x: "Nessuno (Aule/Palestre Separate)" if x.startswith("Nessuno") else f"{problem.rooms[x].name} (Capienza: {problem.rooms[x].capacity})",
                key=f"{key_prefix}_preset_mot_room"
            )
            
            if st.button("⚡ Genera Coppie per Scienze Motorie", type="primary", use_container_width=True, key=f"{key_prefix}_btn_gen_mot_pairs"):
                classes_by_grade = {}
                for cid, c in sorted(problem.classes.items(), key=lambda x: x[1].name):
                    g = getattr(c, "grade", None) or (int(c.name[0]) if c.name and c.name[0].isdigit() else 1)
                    classes_by_grade.setdefault(g, []).append(cid)
                    
                target_grades = [1, 2, 3]
                if "Terze" in target_grade_mot: target_grades = [3]
                elif "Seconde" in target_grade_mot: target_grades = [2]
                elif "Prime" in target_grade_mot: target_grades = [1]
                
                created_count = 0
                for g in target_grades:
                    cl_list = classes_by_grade.get(g, [])
                    if len(cl_list) >= 2:
                        half = len(cl_list) // 2
                        first_half = cl_list[:half]
                        second_half = cl_list[half:half*2]
                        for i in range(len(first_half)):
                            c1 = first_half[i]
                            c2 = second_half[i]
                            c1_name = problem.classes[c1].name
                            c2_name = problem.classes[c2].name
                            
                            a1 = next((a for a in problem.assignments if a.class_id == c1 and a.subject_id == "mot"), None)
                            a2 = next((a for a in problem.assignments if a.class_id == c2 and a.subject_id == "mot"), None)
                            same_t = (a1 and a2 and a1.teacher_id == a2.teacher_id)
                            
                            g_id = f"par_mot_{c1}_{c2}".lower()
                            problem.config.parallel_groups = [pg for pg in problem.config.parallel_groups if pg.id != g_id]
                            
                            chosen_room_id = sel_mot_room if not sel_mot_room.startswith("Nessuno") else None
                            if chosen_room_id and chosen_room_id in problem.rooms:
                                problem.rooms[chosen_room_id].capacity = max(problem.rooms[chosen_room_id].capacity, 2)
                                
                            problem.config.parallel_groups.append(ParallelGroup(
                                id=g_id,
                                name=f"Scienze Motorie: {c1_name} + {c2_name}",
                                subject_id="mot",
                                class_ids=[c1, c2],
                                parallel_hours=2,
                                force_consecutive_block=True,
                                room_id=chosen_room_id,
                                is_same_teacher_merged=same_t,
                                is_active=True
                            ))
                            created_count += 1
                
                st.session_state.result = None
                st.success(f"✅ Create con successo {created_count} coppie di classi per Scienze Motorie in parallelo!")
                st.rerun()
                
        with p_col2:
            st.markdown("##### 📚 Preset 2: Parallelismo Intero Anno di Corso (es. Tutte le Prime)")
            st.caption("Sincronizza tutte le sezioni di un anno di corso sulla stessa materia per fare attività congiunte, recupero o rotazione.")
            
            sel_p_subj = st.selectbox(
                "Materia da sincronizzare:",
                options=list(problem.subjects.keys()),
                index=list(problem.subjects.keys()).index("ita") if "ita" in problem.subjects else 0,
                format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x,
                key=f"{key_prefix}_preset_full_subj"
            )
            
            sel_p_grade = st.selectbox(
                "Anno di corso:",
                options=["Classi Prime (1ª)", "Classi Seconde (2ª)", "Classi Terze (3ª)"],
                key=f"{key_prefix}_preset_full_grade"
            )
            
            p_hours_input = st.number_input(
                "Ore in contemporanea settimanali:",
                min_value=1, max_value=6, value=2,
                key=f"{key_prefix}_preset_full_hours",
                help="Quante ore settimanali devono svolgersi nello stesso momento per tutte le classi dell'anno."
            )
            
            if st.button("⚡ Sincronizza Intero Anno di Corso", type="primary", use_container_width=True, key=f"{key_prefix}_btn_gen_full_grade"):
                g_num = 1 if "Prime" in sel_p_grade else (2 if "Seconde" in sel_p_grade else 3)
                matched_classes = [
                    cid for cid, c in sorted(problem.classes.items(), key=lambda x: x[1].name)
                    if (getattr(c, "grade", None) == g_num or (c.name and c.name.startswith(str(g_num))))
                ]
                
                if len(matched_classes) < 2:
                    st.warning(f"Trovate solo {len(matched_classes)} classi per l'anno selezionato.")
                else:
                    g_id = f"par_full_{sel_p_subj}_g{g_num}".lower()
                    problem.config.parallel_groups = [pg for pg in problem.config.parallel_groups if pg.id != g_id]
                    s_name = problem.subjects[sel_p_subj].name if sel_p_subj in problem.subjects else sel_p_subj
                    grade_label = "Prime" if g_num == 1 else ("Seconde" if g_num == 2 else "Terze")
                    
                    problem.config.parallel_groups.append(ParallelGroup(
                        id=g_id,
                        name=f"{s_name} in Parallelo {grade_label} ({len(matched_classes)} classi)",
                        subject_id=sel_p_subj,
                        class_ids=matched_classes,
                        parallel_hours=p_hours_input,
                        force_consecutive_block=(p_hours_input == 2),
                        room_id=None,
                        is_same_teacher_merged=True,
                        is_active=True
                    ))
                    st.session_state.result = None
                    cl_names = ", ".join(problem.classes[c].name for c in matched_classes)
                    st.success(f"✅ Creato parallelismo per {len(matched_classes)} classi ({cl_names}) su {s_name} ({p_hours_input}h)!")
                    st.rerun()

    # -------------------------------------------------------------
    # 2. CREAZIONE MANUALE DI UN GRUPPO DI PARALLELISMO
    # -------------------------------------------------------------
    with st.expander("➕ Crea Nuovo Gruppo di Classi Aperte Personalizzato", expanded=False):
        c_p1, c_p2 = st.columns(2)
        with c_p1:
            custom_p_name = st.text_input("Nome Regola / Gruppo:", placeholder="es. Laboratorio Scrittura 1A + 1B + 1C", key=f"{key_prefix}_custom_p_name")
            custom_p_subj = st.selectbox(
                "Materia:",
                options=list(problem.subjects.keys()),
                format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x,
                key=f"{key_prefix}_custom_p_subj"
            )
            custom_p_classes = st.multiselect(
                "Classi che fanno lezione contemporaneamente:",
                options=list(problem.classes.keys()),
                format_func=lambda x: f"Classe {problem.classes[x].name}" if x in problem.classes else x,
                key=f"{key_prefix}_custom_p_classes"
            )
        with c_p2:
            custom_p_hours = st.number_input("Ore in contemporanea:", min_value=1, max_value=6, value=2, key=f"{key_prefix}_custom_p_hours")
            custom_p_consec = st.checkbox("Forza le ore in un blocco consecutivo nello stesso giorno", value=True, key=f"{key_prefix}_custom_p_consec")
            
            all_r_opts = ["Nessuno / Aule Separate"] + list(problem.rooms.keys())
            custom_p_room = st.selectbox(
                "Spazio Condiviso (opzionale):",
                options=all_r_opts,
                format_func=lambda x: "Nessuno (Aule Separate)" if x.startswith("Nessuno") else f"{problem.rooms[x].name} (Capienza: {problem.rooms[x].capacity})",
                key=f"{key_prefix}_custom_p_room"
            )
            custom_p_merged = st.checkbox("Docente unico accorpato / Compresenza (le classi sono seguite insieme dallo stesso docente)", value=False, key=f"{key_prefix}_custom_p_merged")

        if st.button("➕ Salva Regola Classi Aperte", type="primary", use_container_width=True, key=f"{key_prefix}_btn_save_custom_par"):
            if not custom_p_name:
                st.warning("Inserisci un nome descrittivo per la regola.")
            elif len(custom_p_classes) < 2:
                st.warning("Seleziona almeno 2 classi da sincronizzare.")
            else:
                new_pg_id = f"par_custom_{int(time.time())}"
                r_val = custom_p_room if not custom_p_room.startswith("Nessuno") else None
                if r_val and r_val in problem.rooms:
                    problem.rooms[r_val].capacity = max(problem.rooms[r_val].capacity, len(custom_p_classes))
                    
                problem.config.parallel_groups.append(ParallelGroup(
                    id=new_pg_id,
                    name=custom_p_name,
                    subject_id=custom_p_subj,
                    class_ids=custom_p_classes,
                    parallel_hours=custom_p_hours,
                    force_consecutive_block=custom_p_consec,
                    room_id=r_val,
                    is_same_teacher_merged=custom_p_merged,
                    is_active=True
                ))
                st.session_state.result = None
                st.success(f"✅ Regola '{custom_p_name}' aggiunta con successo!")
                st.rerun()

    # -------------------------------------------------------------
    # 3. ELENCO DEI GRUPPI ATTUALI
    # -------------------------------------------------------------
    if problem.config.parallel_groups:
        st.markdown(f"##### 📋 Regole Classi Aperte & Parallelismi Configurate ({len(problem.config.parallel_groups)})")
        
        for idx, grp in enumerate(problem.config.parallel_groups):
            s_name = problem.subjects[grp.subject_id].name if grp.subject_id in problem.subjects else grp.subject_id
            cl_names = ", ".join(problem.classes[c].name for c in grp.class_ids if c in problem.classes)
            r_label = problem.rooms[grp.room_id].name if (grp.room_id and grp.room_id in problem.rooms) else "Aule Separate"
            
            with st.container():
                col_info, col_toggle, col_del = st.columns([5, 2, 1])
                with col_info:
                    status_dot = "🟢" if grp.is_active else "⚪"
                    st.markdown(f"**{status_dot} {grp.name}**")
                    st.caption(f"📚 Materia: **{s_name}** | 🏫 Classi: **{cl_names}** | ⏱️ **{grp.parallel_hours}h** {'(Blocco 2h)' if grp.force_consecutive_block else ''} | 🏢 Spazio: *{r_label}*")
                with col_toggle:
                    st.write("")
                    new_act = st.toggle("Attiva", value=grp.is_active, key=f"tgl_par_{grp.id}_{idx}")
                    if new_act != grp.is_active:
                        grp.is_active = new_act
                        st.session_state.result = None
                        st.rerun()
                with col_del:
                    st.write("")
                    if st.button("🗑️", key=f"del_par_{grp.id}_{idx}", help=f"Elimina regola {grp.name}"):
                        problem.config.parallel_groups = [pg for pg in problem.config.parallel_groups if pg.id != grp.id]
                        st.session_state.result = None
                        st.rerun()
                st.markdown("<hr style='margin: 4px 0 10px 0;'>", unsafe_allow_html=True)
                
        if st.button("🗑️ Elimina TUTTI i Parallelismi / Classi Aperte", key=f"{key_prefix}_del_all_par"):
            problem.config.parallel_groups.clear()
            st.session_state.result = None
            st.success("Tutte le regole di classi aperte sono state rimosse.")
            st.rerun()
    else:
        st.info("ℹ️ Nessun parallelismo o classe aperta configurata. Usa i generatori rapidi sopra per creare le coppie di palestra o i parallelismi d'anno.")

def render_optimization_criteria_panel(problem: TimetableProblem, key_prefix: str = "main"):
    """Pannello interattivo per visualizzare e modificare i criteri di assegnazione oraria, tetto ore buche ed equità."""
    st.markdown("#### ⚖️ Criteri di Assegnazione Oraria, Tetto Ore Buche & Equità Docenti")
    st.caption("Controlla e personalizza i vincoli di calcolo, il tetto massimo delle ore buche e la distribuzione omogenea del carico tra i docenti.")

    if not hasattr(problem.config, "optimization_criteria") or problem.config.optimization_criteria is None:
        problem.config.optimization_criteria = OptimizationCriteria()

    crit = problem.config.optimization_criteria

    crit_preset_key = f"{key_prefix}_active_criteria_preset"
    if crit_preset_key not in st.session_state:
        st.session_state[crit_preset_key] = "balanced"

    # Inizializza tutte le chiavi widget in session_state se non presenti
    if f"{key_prefix}_slider_max_gaps" not in st.session_state:
        st.session_state[f"{key_prefix}_slider_max_gaps"] = int(crit.max_gap_limit) if crit.max_gap_limit else 5
    if f"{key_prefix}_chk_strict_gaps" not in st.session_state:
        st.session_state[f"{key_prefix}_chk_strict_gaps"] = bool(crit.strict_gap_limit)
    if f"{key_prefix}_chk_gap_fairness" not in st.session_state:
        st.session_state[f"{key_prefix}_chk_gap_fairness"] = bool(crit.enable_gap_fairness)
    if f"{key_prefix}_w_fd1" not in st.session_state:
        st.session_state[f"{key_prefix}_w_fd1"] = int(crit.weight_free_day_1)
    if f"{key_prefix}_w_fd2" not in st.session_state:
        st.session_state[f"{key_prefix}_w_fd2"] = int(crit.weight_free_day_2)
    if f"{key_prefix}_w_late" not in st.session_state:
        st.session_state[f"{key_prefix}_w_late"] = int(crit.weight_late_entry)
    if f"{key_prefix}_w_early" not in st.session_state:
        st.session_state[f"{key_prefix}_w_early"] = int(crit.weight_early_exit)
    if f"{key_prefix}_w_gap_gen" not in st.session_state:
        st.session_state[f"{key_prefix}_w_gap_gen"] = int(crit.weight_gap_hours)
    if f"{key_prefix}_w_soft" not in st.session_state:
        st.session_state[f"{key_prefix}_w_soft"] = int(crit.weight_soft_slots)

    def apply_crit_preset(preset_name: str):
        st.session_state[crit_preset_key] = preset_name
        if preset_name == "balanced":
            crit.max_gap_limit = 5
            crit.strict_gap_limit = False
            crit.enable_gap_fairness = True
            crit.weight_gap_fairness = 180
            crit.weight_gap_hours = 80
            crit.weight_free_day_1 = 200
            crit.weight_free_day_2 = 120
            crit.weight_late_entry = 80
            crit.weight_early_exit = 80
            crit.weight_soft_slots = 50
        elif preset_name == "docenti":
            crit.max_gap_limit = 6
            crit.strict_gap_limit = False
            crit.enable_gap_fairness = True
            crit.weight_gap_fairness = 100
            crit.weight_gap_hours = 50
            crit.weight_free_day_1 = 400
            crit.weight_free_day_2 = 250
            crit.weight_late_entry = 150
            crit.weight_early_exit = 150
            crit.weight_soft_slots = 100
        elif preset_name == "compact":
            crit.max_gap_limit = 4
            crit.strict_gap_limit = False
            crit.enable_gap_fairness = True
            crit.weight_gap_fairness = 250
            crit.weight_gap_hours = 150
            crit.weight_free_day_1 = 150
            crit.weight_free_day_2 = 80
            crit.weight_late_entry = 60
            crit.weight_early_exit = 60
            crit.weight_soft_slots = 30
        
        # AGGIORNA TUTTI I WIDGET IN SESSION_STATE PERFETTAMENTE
        st.session_state[f"{key_prefix}_slider_max_gaps"] = int(crit.max_gap_limit)
        st.session_state[f"{key_prefix}_chk_strict_gaps"] = bool(crit.strict_gap_limit)
        st.session_state[f"{key_prefix}_chk_gap_fairness"] = bool(crit.enable_gap_fairness)
        st.session_state[f"{key_prefix}_w_fd1"] = int(crit.weight_free_day_1)
        st.session_state[f"{key_prefix}_w_fd2"] = int(crit.weight_free_day_2)
        st.session_state[f"{key_prefix}_w_late"] = int(crit.weight_late_entry)
        st.session_state[f"{key_prefix}_w_early"] = int(crit.weight_early_exit)
        st.session_state[f"{key_prefix}_w_gap_gen"] = int(crit.weight_gap_hours)
        st.session_state[f"{key_prefix}_w_soft"] = int(crit.weight_soft_slots)

    def on_custom_crit_change():
        st.session_state[crit_preset_key] = "custom"
        crit.max_gap_limit = st.session_state[f"{key_prefix}_slider_max_gaps"]
        crit.strict_gap_limit = st.session_state[f"{key_prefix}_chk_strict_gaps"]
        crit.enable_gap_fairness = st.session_state[f"{key_prefix}_chk_gap_fairness"]
        crit.weight_free_day_1 = st.session_state[f"{key_prefix}_w_fd1"]
        crit.weight_free_day_2 = st.session_state[f"{key_prefix}_w_fd2"]
        crit.weight_late_entry = st.session_state[f"{key_prefix}_w_late"]
        crit.weight_early_exit = st.session_state[f"{key_prefix}_w_early"]
        crit.weight_gap_hours = st.session_state[f"{key_prefix}_w_gap_gen"]
        crit.weight_soft_slots = st.session_state[f"{key_prefix}_w_soft"]

    cur_c = st.session_state[crit_preset_key]

    # Box Riepilogo Gerarchico
    with st.expander("ℹ️ **Riepilogo dei Criteri di Assegnazione Oraria (Tassativi vs Ottimizzabili)**", expanded=False):
        c_desc1, c_desc2 = st.columns(2)
        with c_desc1:
            st.markdown("##### 🛡️ 1. Vincoli Tassativi (100% Garantiti)")
            st.markdown(
                """
                - 🚫 **Nessuna Sovrapposizione Docente**: 1 docente in max 1 classe per ora.
                - 🚫 **Nessuna Sovrapposizione Classe**: 1 classe in max 1 materia per ora.
                - 🏛️ **Capienza Aule & Laboratori**: max 1 classe per aula/palestra nello stesso slot.
                - 🔴 **Indisponibilità Assolute (L.104/COE/Part-time)**: docente MAI presente negli slot sbarrati.
                - 🔒 **Accoppiamento a 2 Ore**: blocchi consecutivi rigidi per le materie flaggate.
                - 🛑 **Tetto Massimo Ore Buche**: nessun docente può superare il tetto impostato.
                """
            )
        with c_desc2:
            st.markdown("##### 🎯 2. Obiettivi di Ottimizzazione & Equità")
            st.markdown(
                """
                - ⚖️ **Equità Distribuzione Buche**: bilancia le ore buche in modo simile tra tutti i colleghi.
                - 🏖️ **Giorno Libero**: massimizza 1ª scelta (peso alto) e 2ª scelta.
                - 🌅 **Ingressi Posticipati (No 1ª ora)**: soddisfa le mattine richieste.
                - 🌇 **Uscite Anticipate (No Ult. ora)**: soddisfa i pomeriggi richiesti.
                - 🟡 **Slot Sconsigliati**: evita le ore non gradite espresse dai docenti.
                """
            )

    # Preset Rapidi di Ottimizzazione con evidenziazione del preset ATTIVO
    st.markdown("##### ⚡ Preset Rapidi di Bilanciamento")
    pr_c1, pr_c2, pr_c3 = st.columns(3)
    with pr_c1:
        is_active_b = (cur_c == "balanced")
        label_b = "✅ ⚖️ Bilanciato & Equo (Attivo)" if is_active_b else "⚖️ Bilanciato & Equo (Consigliato)"
        if st.button(label_b, key=f"{key_prefix}_crit_preset_balanced", type="primary" if is_active_b else "secondary", use_container_width=True):
            apply_crit_preset("balanced")
    with pr_c2:
        is_active_d = (cur_c == "docenti")
        label_d = "✅ 🏖️ Massima Priorità Docenti (Attivo)" if is_active_d else "🏖️ Massima Priorità Desiderata Docenti"
        if st.button(label_d, key=f"{key_prefix}_crit_preset_docenti", type="primary" if is_active_d else "secondary", use_container_width=True):
            apply_crit_preset("docenti")
    with pr_c3:
        is_active_c = (cur_c == "compact")
        label_c = "✅ ⚡ Compatto (Attivo)" if is_active_c else "⚡ Compatto (Minime Buche Assolute)"
        if st.button(label_c, key=f"{key_prefix}_crit_preset_compact", type="primary" if is_active_c else "secondary", use_container_width=True):
            apply_crit_preset("compact")

    st.write("")
    
    # Sezione 1: Tetto Ore Buche & Equità
    col_gap1, col_gap2 = st.columns([1, 1])
    with col_gap1:
        st.markdown("**🛑 Controllo Obiettivo Ore Buche**")
        chosen_slider_gaps = st.slider(
            "Obiettivo Tetto Massimo Ore Buche per Docente (Settimanale)",
            min_value=1,
            max_value=8,
            key=f"{key_prefix}_slider_max_gaps",
            on_change=on_custom_crit_change,
            help="Il motore matematico ottimizzerà e comprimerà le cattedre per mantenere tutti i docenti entro questo numero di ore buche complessive nella settimana."
        )
        crit.max_gap_limit = int(chosen_slider_gaps)
        
        chosen_strict_gaps = st.checkbox(
            "🔒 **Vincolo Tassativo Rigido** (Avanzato - Sconsigliato per scuole > 6 classi o DADA)",
            key=f"{key_prefix}_chk_strict_gaps",
            on_change=on_custom_crit_change,
            help="Se attivo, vieta categoricamente qualsiasi orario con anche solo 1 buca oltre il limite impostato. Attenzione: su scuole medie/superiori (18 classi, DADA, laboratori) blocca le combinazioni di passaggio e può impedire la generazione dell'orario. Lascialo disattivato per ottenere un'ottimizzazione fluida ed efficace."
        )
        crit.strict_gap_limit = bool(chosen_strict_gaps)

    with col_gap2:
        st.markdown("**⚖️ Equità & Distribuzione Omogenea tra Docenti**")
        st.checkbox(
            "🤝 **Distribuisci le ore buche in modo simile tra tutti i docenti**",
            key=f"{key_prefix}_chk_gap_fairness",
            on_change=on_custom_crit_change,
            help="Attiva la funzione di Min-Max Fairness: minimizza il picco massimo di buche per singolo docente e livella il carico tra i colleghi (compatibilmente con i vincoli COE e part-time)."
        )
        if crit.enable_gap_fairness:
            st.caption("✅ *Il motore eviterà che un docente abbia 4 buche e un altro 0: cercherà di assegnare a tutti 1-2 ore buche al massimo.*")
        else:
            st.caption("⚠️ *Senza equità attiva, il solutore minimizza solo la somma complessiva, rischiando concentrazioni di buche su singoli docenti.*")

    # Sezione 2: Pesi dei Desiderata Personalizzabili
    with st.expander("🎛️ **Regolazione Fine Pesi e Priorità Desiderata (Avanzato)**", expanded=False):
        c_w1, c_w2, c_w3 = st.columns(3)
        with c_w1:
            st.slider("Priorità Giorno Libero (1ª Scelta)", 50, 500, step=10, key=f"{key_prefix}_w_fd1", on_change=on_custom_crit_change)
            st.slider("Priorità Giorno Libero (2ª Scelta)", 20, 300, step=10, key=f"{key_prefix}_w_fd2", on_change=on_custom_crit_change)
        with c_w2:
            st.slider("Priorità Entrata Tardi (No 1ª ora)", 10, 250, step=10, key=f"{key_prefix}_w_late", on_change=on_custom_crit_change)
            st.slider("Priorità Uscita Presto (No Ultima ora)", 10, 250, step=10, key=f"{key_prefix}_w_early", on_change=on_custom_crit_change)
        with c_w3:
            st.slider("Peso Minimizzazione Buche Generali", 20, 250, step=10, key=f"{key_prefix}_w_gap_gen", on_change=on_custom_crit_change)
            st.slider("Priorità Evitamento Slot Sconsigliati", 10, 200, step=10, key=f"{key_prefix}_w_soft", on_change=on_custom_crit_change)

# Versione Software Progressiva
APP_VERSION = "v1.1.0"

# Configurazione Pagina Streamlit
st.set_page_config(
    page_title=f"Orario Facile {APP_VERSION} - Scuola Secondaria di I Grado",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stili CSS avanzati con feedback visivo per pulsanti attivi e selezione
st.markdown("""
<style>
/* Evidenziazione pulsanti attivi / selezionati (preset e filtri) */
div[data-testid="stButton"] button[kind="primary"] {
    background: linear-gradient(135deg, #0984e3 0%, #00b894 100%) !important;
    border: 2px solid #00cec9 !important;
    color: white !important;
    font-weight: 700 !important;
    box-shadow: 0 0 12px rgba(0, 206, 201, 0.45) !important;
    border-radius: 8px !important;
    transition: all 0.25s ease !important;
}

div[data-testid="stButton"] button[kind="secondary"] {
    border: 1.5px solid #dcdde1 !important;
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}

div[data-testid="stButton"] button[kind="secondary"]:hover {
    border-color: #0984e3 !important;
    color: #0984e3 !important;
    box-shadow: 0 0 8px rgba(9, 132, 227, 0.2) !important;
}

/* Stile compatto e coerente per i selettori numerici (Number Input) */
div[data-testid="stNumberInput"] div[data-baseweb="input"] {
    border-radius: 8px !important;
    transition: all 0.2s ease !important;
}

div[data-testid="stNumberInput"] input {
    font-weight: 700 !important;
    font-size: 1rem !important;
    text-align: center !important;
    padding: 4px 8px !important;
}

div[data-testid="stNumberInput"] button {
    border-radius: 6px !important;
    margin: 2px !important;
    opacity: 0.85 !important;
}

div[data-testid="stNumberInput"] button:hover {
    opacity: 1 !important;
}

/* Stili Banner & Container Modifica Attiva Docenti */
.edit-banner-teacher {
    background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    border: 2.5px solid #2563eb;
    border-left: 8px solid #1d4ed8;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 10px 0 12px 0;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.12);
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.edit-box-teacher-indicator) {
    background-color: #f4f8ff !important;
    border: 2.5px solid #3b82f6 !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 24px rgba(37, 99, 235, 0.15) !important;
    padding: 16px 20px !important;
    margin-bottom: 25px !important;
}

/* Tipografia elegante e compatta per titoli (h1, h2, h3) */
h1 {
    font-size: 1.65rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
    margin-top: 0.2rem !important;
    margin-bottom: 0.6rem !important;
}

h2 {
    font-size: 1.35rem !important;
    font-weight: 750 !important;
    letter-spacing: -0.01em !important;
    margin-top: 0.4rem !important;
    margin-bottom: 0.5rem !important;
}

h3 {
    font-size: 1.18rem !important;
    font-weight: 700 !important;
    margin-top: 0.3rem !important;
    margin-bottom: 0.4rem !important;
}

h4 {
    font-size: 1.05rem !important;
    font-weight: 650 !important;
    margin-top: 0.2rem !important;
    margin-bottom: 0.3rem !important;
}

h5 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
}

/* Stili Schede Tab Superiori compatti ed eleganti */
button[data-baseweb="tab"] {
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    padding: 8px 14px !important;
}

/* Stili Banner & Container Modifica Attiva Aule */
.edit-banner-room {
    background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
    border: 2.5px solid #16a34a;
    border-left: 8px solid #15803d;
    border-radius: 10px;
    padding: 14px 18px;
    margin: 10px 0 12px 0;
    box-shadow: 0 4px 14px rgba(34, 197, 94, 0.12);
}

div[data-testid="stVerticalBlockBorderWrapper"]:has(.edit-box-room-indicator) {
    background-color: #f2fcf5 !important;
    border: 2.5px solid #22c55e !important;
    border-radius: 12px !important;
    box-shadow: 0 6px 24px rgba(34, 197, 94, 0.15) !important;
    padding: 16px 20px !important;
    margin-bottom: 25px !important;
}

/* Modalità Scura */
@media (prefers-color-scheme: dark) {
    .edit-banner-teacher {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border-color: #38bdf8;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.edit-box-teacher-indicator) {
        background-color: #0f172a !important;
        border-color: #38bdf8 !important;
        box-shadow: 0 6px 24px rgba(56, 189, 248, 0.25) !important;
    }
    .edit-banner-room {
        background: linear-gradient(135deg, #064e3b 0%, #022c22 100%);
        border-color: #34d399;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:has(.edit-box-room-indicator) {
        background-color: #064e3b !important;
        border-color: #34d399 !important;
        box-shadow: 0 6px 24px rgba(52, 211, 153, 0.25) !important;
    }
}

/* ------------------------------------------------------------- */
/* SCHEDE PRINCIPALI A PILLOLE (TOP-LEVEL MAIN TABS)             */
/* ------------------------------------------------------------- */
div[data-testid="stAppViewBlockContainer"] > div:first-child div[data-testid="stTabs"] > div[role="tablist"],
.main div[data-testid="stTabs"]:first-child > div[role="tablist"],
.stApp div[data-testid="stTabs"] > div:first-child {
    position: sticky !important;
    top: 2.875rem !important;
    z-index: 999 !important;
    background-color: rgba(125, 125, 125, 0.12) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(125, 125, 125, 0.22) !important;
    border-radius: 14px !important;
    padding: 6px !important;
    gap: 6px !important;
    margin-bottom: 24px !important;
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    overflow-x: auto !important;
    overflow-y: hidden !important;
    scrollbar-width: none !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.06) !important;
}

/* Nascondi la linea rossa/arancione di Streamlit ovunque */
div[data-baseweb="tab-highlight"], 
div[data-baseweb="tab-border"], 
div[data-testid="stTabs"] hr,
div[data-testid="stTabs"] > div:first-child::after,
div[data-baseweb="tab-list"]::after,
div[role="tablist"]::after {
    display: none !important;
    height: 0px !important;
    border: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
}

/* Schede Inattive Generali (Sia Principali che Sottoschede) */
div[data-testid="stTabs"] button[data-testid="stTab"], 
div[data-testid="stTabs"] [data-baseweb="tab"], 
div[role="tablist"] button {
    background-color: transparent !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 8px 16px !important;
    font-weight: 600 !important;
    font-size: 0.90rem !important;
    white-space: nowrap !important;
    flex-shrink: 0 !important;
    transition: all 0.2s ease !important;
    margin: 0 !important;
    box-shadow: none !important;
    opacity: 0.78 !important;
}

/* Hover Schede Inattive */
div[data-testid="stTabs"] button[data-testid="stTab"]:hover,
div[data-testid="stTabs"] [data-baseweb="tab"]:hover,
div[role="tablist"] button:hover {
    background-color: rgba(125, 125, 125, 0.18) !important;
    opacity: 1 !important;
}

/* Scheda ATTIVA (Sia Principale che Sottoscheda): Pillola blu con testo bianco nitido */
div[data-testid="stTabs"] button[data-testid="stTab"][aria-selected="true"],
div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"],
div[role="tablist"] button[aria-selected="true"] {
    background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%) !important;
    border: 1px solid #38bdf8 !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.35) !important;
    opacity: 1 !important;
    z-index: 10 !important;
}

div[data-testid="stTabs"] button[data-testid="stTab"][aria-selected="true"] p,
div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] p,
div[role="tablist"] button[aria-selected="true"] p,
div[data-testid="stTabs"] button[data-testid="stTab"][aria-selected="true"] span,
div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] span,
div[role="tablist"] button[aria-selected="true"] span,
div[data-testid="stTabs"] button[data-testid="stTab"][aria-selected="true"] div,
div[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"] div {
    color: #ffffff !important;
    font-weight: 800 !important;
    -webkit-text-fill-color: #ffffff !important;
}
</style>
""", unsafe_allow_html=True)

# Inizializzazione Session State
if "data_version" not in st.session_state:
    st.session_state["data_version"] = 0

if "problem" not in st.session_state:
    st.session_state["problem"] = get_sample_problem(num_classes=18, is_dada=True, with_theater=True)

if "result" not in st.session_state:
    st.session_state["result"] = None

problem: TimetableProblem = st.session_state["problem"]

# Garanzia di compatibilità per problem.config.daily_hours e num_days
if not hasattr(problem.config, "num_days") or not problem.config.num_days:
    problem.config.num_days = 5
if not hasattr(problem.config, "daily_hours") or not problem.config.daily_hours:
    problem.config.daily_hours = [6] * problem.config.num_days
while len(problem.config.daily_hours) < problem.config.num_days:
    problem.config.daily_hours.append(6)

def get_safe_daily_hours(prob: TimetableProblem, d_i: int) -> int:
    if hasattr(prob.config, "daily_hours") and prob.config.daily_hours and d_i < len(prob.config.daily_hours):
        return prob.config.daily_hours[d_i]
    return 6

# Garanzia di compatibilità per sessioni già aperte nel browser
for t in problem.teachers.values():
    if not hasattr(t, "soft_avoid_slots"):
        t.soft_avoid_slots = []
    if not hasattr(t, "preferred_areas") or not t.preferred_areas:
        if "sostegno" in t.name.lower() or "sostegno" in getattr(t, "cdc", "").lower() or "admm" in getattr(t, "cdc", "").lower():
            t.preferred_areas = ["scientifica"] if "1" in t.id or "2" in t.id or "3" in t.id or "4" in t.id or "5" in t.id else (["umanistica"] if "6" in t.id or "7" in t.id or "8" in t.id or "9" in t.id or "10" in t.id else (["artistica"] if "11" in t.id or "12" in t.id or "13" in t.id or "14" in t.id or "15" in t.id else ["lingue"]))
        else:
            t.preferred_areas = []
    if not hasattr(t, "required_slots"):
        t.required_slots = []
    if not hasattr(t, "prefer_late_entry"):
        t.prefer_late_entry = False
    if not hasattr(t, "prefer_early_exit"):
        t.prefer_early_exit = False
    if not hasattr(t, "is_part_time"):
        t.is_part_time = False

# Sincronizzazione automatica assegnazioni sostegno demo (9h + 9h su due casi diversi)
if getattr(problem, "support_assignments", None) and any(sa.hours_per_week == 18 for sa in problem.support_assignments):
    sample_p = get_sample_problem(num_classes=len(problem.classes) or 18, is_dada=problem.config.is_dada, with_theater=True, num_days=problem.config.num_days)
    problem.support_assignments = sample_p.support_assignments
    problem.students_dva = sample_p.students_dva

for a in problem.assignments:
    if not hasattr(a, "pinned_slots"):
        a.pinned_slots = []

for r in problem.rooms.values():
    if not hasattr(r, "subject_ids"):
        r.subject_ids = []
    if not hasattr(r, "teacher_ids"):
        r.teacher_ids = []
    if not hasattr(r, "is_special_lab"):
        r.is_special_lab = False

if "editing_room_id" not in st.session_state:
    st.session_state.editing_room_id = None

# Garanzia di compatibilità per risultati già calcolati in sessione
curr_res_obj = st.session_state.get("result")
if curr_res_obj is not None:
    if not hasattr(curr_res_obj, "late_entry_total"):
        curr_res_obj.late_entry_total = 0
        curr_res_obj.late_entry_satisfied = 0
    if not hasattr(curr_res_obj, "early_exit_total"):
        curr_res_obj.early_exit_total = 0
        curr_res_obj.early_exit_satisfied = 0
    if not hasattr(curr_res_obj, "soft_slots_total"):
        curr_res_obj.soft_slots_total = 0


# =============================================================
# HELPER RENDER FUNCTIONS (INLINE & MODAL EDITORS)
# =============================================================
def get_teacher_subjects_display(t: Teacher, problem: TimetableProblem) -> str:
    t_assigns = [a for a in problem.assignments if a.teacher_id == t.id]
    s_ids = list(dict.fromkeys(a.subject_id for a in t_assigns))
    if s_ids:
        names = [problem.subjects[s].name for s in s_ids if s in problem.subjects]
        if names:
            return ", ".join(names)
    cdc_val = getattr(t, "cdc", "")
    mapping = {
        "A-22": "Italiano, Storia, Geografia",
        "A-28": "Matematica e Scienze",
        "A-24": "Inglese / Seconda Lingua",
        "A-60": "Tecnologia",
        "A-30": "Musica",
        "A-01": "Arte e Immagine",
        "A-48": "Scienze Motorie",
        "Religione": "Religione Cattolica",
        "ADMM": "Sostegno Didattico (ADMM)",
        "Sostegno": "Sostegno Didattico (ADMM)"
    }
    for k, v in mapping.items():
        if k in cdc_val:
            return v
    if "sostegno" in t.name.lower() or "sostegno" in cdc_val.lower() or "admm" in cdc_val.lower():
        return "Sostegno Didattico (ADMM)"
    return cdc_val if cdc_val else "Docente"

def render_teacher_edit_card(problem: TimetableProblem, target_t: Optional[Teacher] = None, is_inline: bool = False):
    is_editing = (target_t is not None)
    t_id_val = target_t.id if is_editing else ""
    t_key_suffix = f"_{t_id_val}" if is_editing else "_new_teacher"
    is_settimana_corta = (problem.config.num_days == 5)
    subject_areas = [
        "Italiano, Storia, Geografia (Lettere)",
        "Matematica e Scienze",
        "Lingua Inglese",
        "Seconda Lingua Comunitaria (Spagnolo / Francese / Tedesco)",
        "Tecnologia",
        "Musica",
        "A-56 Strumento Musicale / Musica d'Insieme (Orchestra & Solfeggio)",
        "Arte e Immagine",
        "Scienze Motorie e Sportive",
        "Religione Cattolica",
        "Sostegno / Altra Disciplina"
    ]
    
    # 1. Dati Anagrafici & Tipo Contratto
    st.markdown("#### 👤 1. Dati Anagrafici & Tipo Contratto")
    c_t1, c_t2 = st.columns([3, 2])
    with c_t1:
        if is_editing:
            t_id = st.text_input("ID Docente", value=target_t.id, disabled=True, key=f"edit_t_id{t_key_suffix}")
            t_name = st.text_input("Nome e Cognome Docente", value=target_t.name, key=f"edit_t_name{t_key_suffix}")
        else:
            t_name = st.text_input("Nome e Cognome Docente", placeholder="es. Prof. Mario Rossi", key=f"new_t_name{t_key_suffix}")
            t_id = f"doc_{t_name.lower().replace(' ', '_').replace('.', '')}" if t_name else ""
            
        cur_t_cdc = getattr(target_t, "cdc", "") if is_editing else ""
        cdc_idx = 0
        for i_c, c_str in enumerate(subject_areas):
            if cur_t_cdc and (
                cur_t_cdc.lower() in c_str.lower() 
                or c_str.lower() in cur_t_cdc.lower()
                or ("a-56" in cur_t_cdc.lower() and "a-56" in c_str.lower())
                or ("chitarra" in cur_t_cdc.lower() and "a-56" in c_str.lower())
                or ("violino" in cur_t_cdc.lower() and "a-56" in c_str.lower())
                or ("flauto" in cur_t_cdc.lower() and "a-56" in c_str.lower())
                or ("clarinetto" in cur_t_cdc.lower() and "a-56" in c_str.lower())
                or ("a-22" in cur_t_cdc and "Lettere" in c_str) 
                or ("a-28" in cur_t_cdc and "Matematica" in c_str) 
                or ("a-24" in cur_t_cdc and "Inglese" in c_str) 
                or ("a-60" in cur_t_cdc and "Tecnologia" in c_str) 
                or ("a-30" in cur_t_cdc and "Musica" in c_str and "A-56" not in cur_t_cdc) 
                or ("a-01" in cur_t_cdc and "Arte" in c_str) 
                or ("a-48" in cur_t_cdc and "Motorie" in c_str)
            ):
                cdc_idx = i_c
                break
        t_cdc_label = st.selectbox("Materia / Area di Insegnamento", subject_areas, index=cdc_idx, key=f"t_cdc_sel{t_key_suffix}")
        t_cdc = t_cdc_label.split(" (")[0]
        
    with c_t2:
        t_is_pt = st.checkbox("Docente in Part-Time / Orario Ridotto", value=getattr(target_t, "is_part_time", False) if is_editing else False, key=f"t_pt_chk{t_key_suffix}")
        t_contract_h = None
        t_max_working_d = None
        if t_is_pt:
            pt_c1, pt_c2 = st.columns(2)
            with pt_c1:
                init_ch = getattr(target_t, "contract_hours", 9) if is_editing else 9
                t_contract_h = st.number_input("Ore Contratto", min_value=1, max_value=18, value=init_ch or 9, key=f"t_c_hours{t_key_suffix}")
            with pt_c2:
                init_mwd = getattr(target_t, "max_working_days", 3) if is_editing else 3
                t_max_working_d = st.number_input("Max Giorni Presenza", min_value=1, max_value=problem.config.num_days, value=init_mwd or 3, key=f"t_mw_days{t_key_suffix}")
            st.caption(f"🔒 **Vincolo Rigido**: Presenza su al massimo **{t_max_working_d} giorni**.")
        else:
            st.info("💼 **Tempo Pieno Standard**: 18 ore settimanali di cattedra.")
    
    st.divider()
    
    t_current_id = target_t.id if is_editing else "new_teacher"
    temp_key = f"teacher_temp_assigns{t_key_suffix}"
    if temp_key not in st.session_state:
        if is_editing:
            st.session_state[temp_key] = [
                {
                    "class_id": a.class_id,
                    "subject_id": a.subject_id,
                    "hours_per_week": a.hours_per_week,
                    "force_double_hours": problem.config.subject_block_preferences.get(a.subject_id, a.force_double_hours) if (hasattr(problem.config, "subject_block_preferences") and problem.config.subject_block_preferences and a.subject_id in problem.config.subject_block_preferences) else a.force_double_hours,
                    "max_daily_hours": a.max_daily_hours,
                    "co_teacher_ids": getattr(a, "co_teacher_ids", [])
                }
                for a in problem.assignments if (a.teacher_id == target_t.id or target_t.id in getattr(a, "co_teacher_ids", []))
            ]
        else:
            st.session_state[temp_key] = []
    
    temp_assigns = st.session_state[temp_key]
    
    is_support_teacher = (
        "sostegno" in t_cdc_label.lower() 
        or "sostegno" in t_name.lower() 
        or "sostegno" in t_cdc.lower() 
        or "admm" in t_cdc.lower()
        or bool(is_editing and getattr(target_t, "preferred_areas", []))
    )
    
    selected_areas = []
    if is_support_teacher:
        # 2. Aree Disciplinari / Materie di Preferenza per Docenti di Sostegno
        st.markdown("#### 🎯 2. Aree Disciplinari di Preferenza (Sostegno & Compresenze)")
        st.caption("Seleziona gli ambiti disciplinari su cui questo docente ha maggiore affinità o preferisce intervenire per le compresenze e il supporto didattico PEI.")
        
        area_keys = list(DISCIPLINARY_AREAS.keys())
        cur_areas = getattr(target_t, "preferred_areas", []) if is_editing else []
        selected_areas = st.multiselect(
            "Aree Disciplinari di Preferenza:",
            area_keys,
            default=[a for a in cur_areas if a in area_keys],
            format_func=lambda x: f"{DISCIPLINARY_AREAS[x]['label']} ({DISCIPLINARY_AREAS[x]['desc']})",
            key=f"t_pref_areas{t_key_suffix}",
            help="Il solutore collocherà prioritariamente le ore di sostegno di questo docente durante le lezioni delle aree selezionate."
        )
        st.info("ℹ️ **Nota Cattedre & Casi DVA**: L'assegnazione alle classi e agli alunni DVA per questo docente avviene in modo dettagliato nel **Tab 4 (Sostegno & DVA)**.")
    else:
        # 2. Assegnazione Classi e Materie della Cattedra Curricolare
        st.markdown("#### 🏫 2. Assegnazione Classi e Materie della Cattedra")
        st.caption("Assegna le classi e le materie insegnate da questo docente. Il monte ore si aggiorna in tempo reale.")
        
        if problem.classes and problem.subjects:
            c_add1, c_add2, c_add3, c_add4 = st.columns([3, 3, 2, 2])
            with c_add1:
                class_choices = list(problem.classes.keys())
                sel_ac_class = st.selectbox("Classe", class_choices, format_func=lambda x: problem.classes[x].name if x in problem.classes else x, key=f"ac_class_sel{t_key_suffix}")
            with c_add2:
                subj_choices = list(problem.subjects.keys())
                default_s_idx = 0
                if t_cdc:
                    for s_i, s_k in enumerate(subj_choices):
                        if problem.subjects[s_k].cdc == t_cdc or t_cdc in problem.subjects[s_k].cdc:
                            default_s_idx = s_i
                            break
                sel_ac_subj = st.selectbox("Materia", subj_choices, index=default_s_idx, format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x, key=f"ac_subj_sel{t_key_suffix}")
            with c_add3:
                def_hrs = 2
                if sel_ac_subj in ["ita"]: def_hrs = 6
                elif sel_ac_subj in ["mat"]: def_hrs = 4
                elif sel_ac_subj in ["ing"]: def_hrs = 3
                elif sel_ac_subj in ["sci"]: def_hrs = 2
                elif sel_ac_subj in ["rel", "app"]: def_hrs = 1
                sel_ac_hours = st.number_input("Ore Settimanali", min_value=1, max_value=10, value=def_hrs, key=f"ac_hours_inp{t_key_suffix}")
            with c_add4:
                st.write("")
                if st.button("➕ Assegna Classe", key=f"btn_add_to_cattedra{t_key_suffix}", use_container_width=True, type="secondary"):
                    pref_dbl = problem.config.subject_block_preferences.get(sel_ac_subj, sel_ac_hours >= 2)
                    temp_assigns.append({
                        "class_id": sel_ac_class,
                        "subject_id": sel_ac_subj,
                        "hours_per_week": sel_ac_hours,
                        "force_double_hours": pref_dbl and (sel_ac_hours >= 2),
                        "max_daily_hours": 2 if pref_dbl else (1 if sel_ac_hours in [2, 3] else 2)
                    })
                    st.rerun()
        
        if temp_assigns:
            tot_h_doc = sum(item["hours_per_week"] for item in temp_assigns)
            target_h_doc = t_contract_h if (t_is_pt and t_contract_h) else 18
            
            if tot_h_doc == target_h_doc:
                st.success(f"💼 **Monte Ore Assegnato**: **{tot_h_doc} / {target_h_doc} ore** (Cattedra Completa al 100% ✅)")
            elif tot_h_doc < target_h_doc:
                st.warning(f"💼 **Monte Ore Assegnato**: **{tot_h_doc} / {target_h_doc} ore** (Mancano **{target_h_doc - tot_h_doc} ore**)")
            else:
                st.error(f"💼 **Monte Ore Assegnato**: **{tot_h_doc} / {target_h_doc} ore** (Supero di **+{tot_h_doc - target_h_doc} ore**)")
        
            st.markdown("""
            <div style="display: grid; grid-template-columns: 2.8fr 3fr 1.4fr 2fr 0.8fr; gap: 8px; font-weight: 700; color: #1e3a8a; margin: 10px 0 4px 0; font-size: 0.88rem;">
                <div>🏫 Modifica Classe</div>
                <div>📖 Modifica Materia</div>
                <div>⏱️ Ore/sett.</div>
                <div>🔒 Blocco Orario</div>
                <div style="text-align: center;">Elimina</div>
            </div>
            """, unsafe_allow_html=True)
            
            class_keys = list(problem.classes.keys())
            subj_keys = list(problem.subjects.keys())

            for idx_a, item in enumerate(temp_assigns):
                c_row1, c_row2, c_row3, c_row4, c_row5 = st.columns([2.8, 3, 1.4, 2, 0.8])
                with c_row1:
                    cur_c_idx = class_keys.index(item['class_id']) if item['class_id'] in class_keys else 0
                    new_c_id = st.selectbox(
                        "Classe",
                        options=class_keys,
                        index=cur_c_idx,
                        format_func=lambda x: f"Classe {problem.classes[x].name}" if x in problem.classes else x,
                        key=f"t_temp_c_{idx_a}_{item['class_id']}_{t_key_suffix}",
                        label_visibility="collapsed"
                    )
                    if new_c_id != item['class_id']:
                        item['class_id'] = new_c_id
                        st.rerun()

                with c_row2:
                    cur_s_idx = subj_keys.index(item['subject_id']) if item['subject_id'] in subj_keys else 0
                    new_s_id = st.selectbox(
                        "Materia",
                        options=subj_keys,
                        index=cur_s_idx,
                        format_func=lambda x: f"{problem.subjects[x].name}" if x in problem.subjects else x,
                        key=f"t_temp_s_{idx_a}_{item['subject_id']}_{t_key_suffix}",
                        label_visibility="collapsed"
                    )
                    if new_s_id != item['subject_id']:
                        item['subject_id'] = new_s_id
                        st.rerun()

                with c_row3:
                    new_h = st.number_input(
                        "Ore",
                        min_value=1,
                        max_value=10,
                        value=item['hours_per_week'],
                        key=f"t_temp_h_{idx_a}_{t_key_suffix}",
                        label_visibility="collapsed"
                    )
                    item['hours_per_week'] = new_h

                with c_row4:
                    is_ita_sub = (item['subject_id'] == "ita" or "italian" in item['subject_id'].lower())
                    if is_ita_sub and getattr(problem.config, "force_triple_hours_italian", False):
                        st.markdown("📝 **3h Tema 🔒**")
                        item['force_triple_hours'] = True
                        item['force_double_hours'] = False
                        item['max_daily_hours'] = 3
                    else:
                        cur_pref_val = item.get('force_double_hours', False)
                        new_dbl = st.checkbox(
                            "Blocco 2h 🔒",
                            value=bool(cur_pref_val),
                            key=f"t_temp_dbl_{idx_a}_{t_key_suffix}"
                        )
                        item['force_double_hours'] = new_dbl
                        item['force_triple_hours'] = False
                        item['max_daily_hours'] = 2 if new_dbl else (1 if new_h in [2, 3] else 2)

                with c_row5:
                    if st.button("🗑️", key=f"del_temp_a_{idx_a}_{t_key_suffix}", help="Rimuovi questa riga"):
                        temp_assigns.pop(idx_a)
                        st.rerun()
        else:
            st.info("Nessuna classe ancora associata a questo docente. Usa il selettore sopra per aggiungere le classi.")
    
    st.divider()
    
    # 3. Regole di Servizio & Desiderata Didattici della Cattedra
    st.markdown("#### 📚 3. Regole di Servizio & Carico Orario del Docente")
    st.caption("Imposta i vincoli di servizio: ore minime/massime giornaliere e tetto ore continuative di lezione.")
    c_did1, c_did2, c_did3, c_did4 = st.columns(4)
    with c_did1:
        init_mindh = getattr(target_t, "min_daily_hours", 2) if is_editing else 2
        t_min_daily = st.number_input("Minimo ore/giorno (se presente)", min_value=1, max_value=4, value=init_mindh, key=f"t_mindh_inp{t_key_suffix}", help="Se presente a scuola, il docente farà almeno questo numero di ore (mai 1 ora singola da sola).")
    with c_did2:
        init_mdh = target_t.max_daily_hours if is_editing else 5
        t_max_daily = st.number_input("Max ore di lezione al giorno", min_value=2, max_value=8, value=init_mdh, key=f"t_mdh_inp{t_key_suffix}", help="Massimo numero di ore di lezione in una singola giornata (default 5h).")
    with c_did3:
        init_mch = target_t.max_consecutive_hours if is_editing else 4
        t_max_consec = st.number_input("Max ore consecutive", min_value=2, max_value=6, value=init_mch, key=f"t_mch_inp{t_key_suffix}", help="Massimo ore di fila senza pausa (default 4h). Se fa 5 ore in un giorno, viene imposto almeno 1 buco intermedio.")
    with c_did4:
        init_mgh = target_t.max_gap_hours if is_editing else 2
        t_max_gaps = st.number_input("Max ore buche settimanali", min_value=0, max_value=6, value=min(init_mgh, 6), key=f"t_mgh_inp{t_key_suffix}")
    
    st.divider()
    
    # 4. Desiderata Personali del Docente
    st.markdown("#### 🗓️ 4. Desiderata Personali del Docente")
    c_pers1, c_pers2 = st.columns(2)
    with c_pers1:
        days_options = ["Nessuno"] + DAYS_OF_WEEK[:problem.config.num_days]
        selected_free_days = []
        
        if is_settimana_corta:
            if not t_is_pt:
                st.markdown("🏖️ **Giorno Libero**: *Non previsto (Tempo Pieno 5/5 gg. Sabato chiuso).*")
            else:
                max_d = t_max_working_d or 3
                n_free_days = max(5 - max_d, 1)
                st.markdown(f"🏖️ **Giorni Liberi Part-Time** *(fino a **{n_free_days} giorni**)*:")
                cur_f_list = getattr(target_t, "free_days", []) if is_editing else []
                for fd_i in range(n_free_days):
                    init_val = cur_f_list[fd_i] if fd_i < len(cur_f_list) else "Nessuno"
                    idx = days_options.index(init_val) if init_val in days_options else 0
                    chosen = st.selectbox(f"Preferenza {fd_i+1}° Giorno Libero", days_options, index=idx, key=f"t_pt_fd5_{fd_i}{t_key_suffix}")
                    if chosen and chosen != "Nessuno":
                        selected_free_days.append(chosen)
        else:
            if not t_is_pt:
                st.markdown("🏖️ **Giorno Libero Settimanale** *(1 giorno di riposo su 6)*:")
                idx1 = days_options.index(target_t.free_day_1) if (is_editing and target_t.free_day_1 in days_options) else 0
                idx2 = days_options.index(target_t.free_day_2) if (is_editing and target_t.free_day_2 in days_options) else 0
                t_fd1 = st.selectbox("1ª Scelta Giorno Libero", days_options, index=idx1, key=f"t_fd1_sel{t_key_suffix}")
                t_fd2 = st.selectbox("2ª Scelta Giorno Libero", days_options, index=idx2, key=f"t_fd2_sel{t_key_suffix}")
                if t_fd1 and t_fd1 != "Nessuno": selected_free_days.append(t_fd1)
                if t_fd2 and t_fd2 != "Nessuno": selected_free_days.append(t_fd2)
            else:
                max_d = t_max_working_d or 3
                n_free_days = max(6 - max_d, 1)
                st.markdown(f"🏖️ **Giorni Liberi Part-Time** *(fino a **{n_free_days} giorni**)*:")
                cur_f_list = getattr(target_t, "free_days", []) if is_editing else []
                for fd_i in range(n_free_days):
                    init_val = cur_f_list[fd_i] if fd_i < len(cur_f_list) else "Nessuno"
                    idx = days_options.index(init_val) if init_val in days_options else 0
                    chosen = st.selectbox(f"Preferenza {fd_i+1}° Giorno Libero", days_options, index=idx, key=f"t_pt_fd6_{fd_i}{t_key_suffix}")
                    if chosen and chosen != "Nessuno":
                        selected_free_days.append(chosen)
    
    with c_pers2:
        st.markdown("🕒 **Preferenze Puntuali Ingresso / Uscita:**")
        valid_days = DAYS_OF_WEEK[:problem.config.num_days]
        cur_late_days = getattr(target_t, "late_entry_days", []) if is_editing else []
        cur_early_days = getattr(target_t, "early_exit_days", []) if is_editing else []
        
        t_late_days = st.multiselect(
            "🌅 Giorni Entrata Posticipata (No 1ª ora)",
            options=valid_days,
            default=[d for d in cur_late_days if d in valid_days],
            key=f"t_late_days_sel{t_key_suffix}",
            help="Seleziona i giorni specifici in cui il docente preferisce non fare la 1ª ora."
        )
        t_early_days = st.multiselect(
            "🌇 Giorni Uscita Anticipata (No Ultima ora)",
            options=valid_days,
            default=[d for d in cur_early_days if d in valid_days],
            key=f"t_early_days_sel{t_key_suffix}",
            help="Seleziona i giorni specifici in cui il docente preferisce non fare l'ultima ora."
        )
        t_prefer_late = len(t_late_days) > 0
        t_prefer_early = len(t_early_days) > 0

    st.markdown("##### ⏱️ Fasce Orarie & Disponibilità Giornaliere (Mattino / Pomeriggio)")
    st.caption("Imposta facilmente se il docente (es. docente di strumento) lavora solo al **mattino (es. 1ª-4ª ora)** o solo al **pomeriggio (rientri/dopo mensa)**:")

    tab_indisp, tab_req, tab_pin, tab_soft = st.tabs([
        "🔴 1. Escludi in queste ore (MAI Lezione)",
        "🟢 2. Includi in queste ore (DEVE Avere Lezione)",
        "📌 3. Fissa Lezione Specifica (Classe + Materia nello Slot)",
        "🟡 4. Slot Sconsigliati (Evita se Possibile)"
    ])
    
    with tab_indisp:
        st.markdown("##### 🔴 Indisponibilità Tassativa del Docente (NO Lezione)")
        unavail_cols = st.columns(problem.config.num_days)
        selected_unavail = []
        cur_unavail = getattr(target_t, "unavailable_slots", []) if is_editing else []
        for d_i in range(problem.config.num_days):
            with unavail_cols[d_i]:
                st.markdown(f"**{DAYS_OF_WEEK[d_i]}**")
                for h_i in range(get_safe_daily_hours(problem, d_i)):
                    is_pre_checked = [d_i, h_i] in cur_unavail
                    is_unavail = st.checkbox(f"{h_i+1}ª Ora (No)", value=is_pre_checked, key=f"unavail_form_{d_i}_{h_i}{t_key_suffix}")
                    if is_unavail:
                        selected_unavail.append([d_i, h_i])
    
    with tab_req:
        st.markdown("##### 🟢 Presenza Tassativa del Docente (DEVE Avere Lezione)")
        req_cols = st.columns(problem.config.num_days)
        selected_required = []
        cur_required = getattr(target_t, "required_slots", []) if is_editing else []
        for d_i in range(problem.config.num_days):
            with req_cols[d_i]:
                st.markdown(f"**{DAYS_OF_WEEK[d_i]}**")
                for h_i in range(get_safe_daily_hours(problem, d_i)):
                    is_pre_checked = [d_i, h_i] in cur_required
                    is_req = st.checkbox(f"{h_i+1}ª Ora (Fissa 🔒)", value=is_pre_checked, key=f"req_form_{d_i}_{h_i}{t_key_suffix}")
                    if is_req:
                        selected_required.append([d_i, h_i])
    
    with tab_pin:
        st.markdown("##### 📌 Pre-Fissaggio Lezione Specifica (Classe + Disciplina nello Slot)")
        doc_class_options = sorted(list(set(item["class_id"] for item in temp_assigns)))
        if doc_class_options:
            p_c1, p_c2, p_c3, p_c4, p_c5 = st.columns([3, 3, 2, 2, 2])
            with p_c1:
                pin_class = st.selectbox("Classe da Fissare", doc_class_options, format_func=lambda x: problem.classes[x].name if x in problem.classes else x, key=f"pin_c_sel{t_key_suffix}")
            with p_c2:
                subjs_for_class = [item["subject_id"] for item in temp_assigns if item["class_id"] == pin_class]
                pin_subj = st.selectbox("Materia da Fissare", subjs_for_class, format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x, key=f"pin_s_sel{t_key_suffix}")
            with p_c3:
                pin_day_label = st.selectbox("Giorno", DAYS_OF_WEEK[:problem.config.num_days], key=f"pin_day_sel{t_key_suffix}")
                pin_day_idx = DAYS_OF_WEEK.index(pin_day_label)
            with p_c4:
                pin_h_idx = st.selectbox("Ora", list(range(get_safe_daily_hours(problem, pin_day_idx))), format_func=lambda x: f"{x+1}ª Ora", key=f"pin_h_sel{t_key_suffix}")
            with p_c5:
                st.write("")
                if st.button("📌 Blocca", key=f"btn_add_pin{t_key_suffix}", use_container_width=True, type="primary"):
                    target_assign = next((a for a in problem.assignments if (is_editing and a.teacher_id == target_t.id) and a.class_id == pin_class and a.subject_id == pin_subj), None)
                    if target_assign:
                        if not hasattr(target_assign, "pinned_slots"):
                            target_assign.pinned_slots = []
                        if [pin_day_idx, pin_h_idx] not in target_assign.pinned_slots:
                            target_assign.pinned_slots.append([pin_day_idx, pin_h_idx])
                            st.success(f"📌 Lezione bloccata su {pin_day_label} alla {pin_h_idx+1}ª ora!")
                            st.rerun()
    
            pinned_items = []
            if is_editing:
                for a in problem.assignments:
                    if a.teacher_id == target_t.id and getattr(a, "pinned_slots", []):
                        for p_slot in a.pinned_slots:
                            pinned_items.append((a, p_slot))
    
            if pinned_items:
                st.markdown("###### 📋 Lezioni Attualmente Fissate / Bloccate:")
                for p_idx, (a_obj, p_slot) in enumerate(pinned_items):
                    c_p1, c_p2, c_p3, c_p4 = st.columns([3, 3, 3, 1])
                    c_name = problem.classes[a_obj.class_id].name if a_obj.class_id in problem.classes else a_obj.class_id
                    s_name = problem.subjects[a_obj.subject_id].name if a_obj.subject_id in problem.subjects else a_obj.subject_id
                    d_name = DAYS_OF_WEEK[p_slot[0]]
                    with c_p1: st.write(f"🏫 **Classe {c_name}**")
                    with c_p2: st.write(f"📖 {s_name}")
                    with c_p3: st.markdown(f"🗓️ **{d_name}**, **{p_slot[1]+1}ª Ora** 🔒")
                    with c_p4:
                        if st.button("🗑️", key=f"del_pin_{p_idx}{t_key_suffix}", help="Sblocca questa lezione"):
                            a_obj.pinned_slots.remove(p_slot)
                            st.rerun()
    
    with tab_soft:
        st.markdown("##### 🟡 Slot Sconsigliati (Vincolo Soft / Non Graditi)")
        soft_cols = st.columns(problem.config.num_days)
        selected_soft = []
        cur_soft = getattr(target_t, "soft_avoid_slots", []) if is_editing else []
        for d_i in range(problem.config.num_days):
            with soft_cols[d_i]:
                st.markdown(f"**{DAYS_OF_WEEK[d_i]}**")
                for h_i in range(get_safe_daily_hours(problem, d_i)):
                    is_pre_checked = [d_i, h_i] in cur_soft
                    is_soft = st.checkbox(f"{h_i+1}ª Ora (Evita)", value=is_pre_checked, key=f"soft_form_{d_i}_{h_i}{t_key_suffix}")
                    if is_soft:
                        selected_soft.append([d_i, h_i])
    
    st.divider()
    
    # Pulsanti di Salvataggio
    col_save_btn1, col_save_btn2 = st.columns([2, 1])
    with col_save_btn1:
        save_label = "💾 Salva Modifiche Docente" if is_editing else "💾 Inserisci Nuovo Docente"
        if st.button(save_label, type="primary", use_container_width=True, key=f"btn_save_teacher{t_key_suffix}"):
            if t_id and t_name:
                updated_t = create_safe_teacher(
                    id=t_id,
                    name=t_name,
                    cdc=t_cdc,
                    is_part_time=t_is_pt,
                    contract_hours=t_contract_h if t_is_pt else None,
                    max_working_days=t_max_working_d if t_is_pt else None,
                    free_days=selected_free_days,
                    preferred_areas=selected_areas,
                    unavailable_slots=selected_unavail,
                    required_slots=selected_required,
                    prefer_late_entry=t_prefer_late,
                    prefer_early_exit=t_prefer_early,
                    late_entry_days=t_late_days,
                    early_exit_days=t_early_days,
                    soft_avoid_slots=selected_soft,
                    min_daily_hours=t_min_daily,
                    max_daily_hours=t_max_daily,
                    max_consecutive_hours=t_max_consec,
                    max_gap_hours=t_max_gaps
                )
                problem.teachers[t_id] = updated_t
                
                old_pins_by_key = {}
                old_co_by_key = {}
                for old_a in problem.assignments:
                    if old_a.teacher_id == t_id and getattr(old_a, "pinned_slots", []):
                        old_pins_by_key[(old_a.class_id, old_a.subject_id)] = old_a.pinned_slots
                    if getattr(old_a, "co_teacher_ids", []):
                        old_co_by_key[(old_a.class_id, old_a.subject_id)] = old_a.co_teacher_ids
    
                problem.assignments = [a for a in problem.assignments if a.teacher_id != t_id]
                if not is_support_teacher:
                    for idx_a, item in enumerate(temp_assigns):
                        # Se questa cattedra era una compresenza con un altro docente titolare, mantieni il titolare e la compresenza
                        item_co = item.get("co_teacher_ids", []) or old_co_by_key.get((item["class_id"], item["subject_id"]), [])
                        assign_id = f"a_{t_id}_{item['class_id']}_{item['subject_id']}_{idx_a}".lower().replace(" ", "_")
                        saved_pins = old_pins_by_key.get((item["class_id"], item["subject_id"]), [])
                        problem.assignments.append(TeachingAssignment(
                            id=assign_id,
                            teacher_id=t_id,
                            class_id=item["class_id"],
                            subject_id=item["subject_id"],
                            hours_per_week=item["hours_per_week"],
                            force_double_hours=item.get("force_double_hours", False),
                            force_triple_hours=item.get("force_triple_hours", False),
                            max_daily_hours=item.get("max_daily_hours", 2),
                            pinned_slots=saved_pins,
                            co_teacher_ids=item_co,
                            preferred_time_of_day="morning_only" if (item["subject_id"] in ["orch", "solf"]) else "any"
                        ))
    
                # Pulisci tutti i widget memorizzati per questo docente
                for k in list(st.session_state.keys()):
                    if k.endswith(f"_{t_id}") or f"_{t_id}_" in k or k.startswith(f"teacher_temp_assigns_{t_id}"):
                        del st.session_state[k]

                st.session_state["problem"] = problem
                st.session_state["result"] = None
                st.session_state.editing_teacher_id = None
                st.session_state["teacher_save_success"] = f"✅ Docente '{t_name}', cattedra e desiderata salvati con successo!"
                st.rerun()
            else:
                st.error("Inserisci Nome e Cognome del docente.")
                
    with col_save_btn2:
        if is_editing:
            if st.button("❌ Chiudi / Annulla Modifica", use_container_width=True, key=f"btn_cancel_teacher{t_key_suffix}"):
                for k in list(st.session_state.keys()):
                    if k.endswith(f"_{t_id}") or f"_{t_id}_" in k or k.startswith(f"teacher_temp_assigns_{t_id}"):
                        del st.session_state[k]
                st.session_state.editing_teacher_id = None
                st.rerun()


def render_room_edit_card(problem: TimetableProblem, target_r: Optional[Classroom] = None, is_inline: bool = False):
    is_editing_room = (target_r is not None)
    r_id_val = target_r.id if is_editing_room else ""
    r_key_suffix = f"_{r_id_val}" if is_editing_room else "_new_room"
    
    c_r1, c_r2 = st.columns(2)
    with c_r1:
        if is_editing_room:
            st.text_input("ID Univoco Aula (Non modificabile)", value=target_r.id, disabled=True, key=f"room_id_fld{r_key_suffix}")
            r_id_input = target_r.id
        else:
            r_id_input = st.text_input("ID Univoco Aula", placeholder="es. aula_101, lab_lingue, aula_mat_1", key=f"room_id_fld{r_key_suffix}")
        
        init_r_name = target_r.name if is_editing_room else ""
        r_name_input = st.text_input("Nome Aula / Laboratorio", value=init_r_name, placeholder="es. Aula 1ª A, Laboratorio di Coding, Aula Matematica & Scienze", key=f"room_name_fld{r_key_suffix}")
    
    with c_r2:
        init_r_type = 1 if (is_editing_room and target_r.is_special_lab) else 0
        r_type_choice = st.radio("Tipologia Spazio:", ["Aula Ordinaria / Dipartimentale / DADA", "Laboratorio Speciale / Palestra / Spazio Esclusivo"], index=init_r_type, key=f"room_type_rad{r_key_suffix}")
        
        c_cap1, c_cap2 = st.columns(2)
        with c_cap1:
            init_r_cap = target_r.capacity if is_editing_room else 1
            r_cap_input = st.number_input("Capienza (N° Classi):", min_value=1, max_value=5, value=init_r_cap, help="Quante classi possono utilizzare questo spazio nello stesso momento.", key=f"room_cap_fld{r_key_suffix}")
        with c_cap2:
            init_r_prio = getattr(target_r, "priority", 1) if is_editing_room else 1
            prio_options = [1, 2, 3]
            r_prio_input = st.selectbox(
                "Priorità Spazio:",
                options=prio_options,
                index=prio_options.index(init_r_prio) if init_r_prio in prio_options else 0,
                format_func=lambda p: {
                    1: "🥇 Priorità 1 (Principale)",
                    2: "🥈 Priorità 2 (Secondaria)",
                    3: "🥉 Priorità 3 (Di Riserva)"
                }.get(p, f"Priorità {p}"),
                help="Se più spazi sono compatibili con una materia, il solutore assegnerà per primo lo spazio a Priorità 1.",
                key=f"room_priority_fld{r_key_suffix}"
            )

    c_r3, c_r4 = st.columns(2)
    with c_r3:
        init_subjs = [s for s in target_r.subject_ids if s in problem.subjects] if is_editing_room else []
        r_subjs_choice = st.multiselect(
            "📚 Materie autorizzate (opzionale):",
            options=list(problem.subjects.keys()),
            default=init_subjs,
            format_func=lambda x: f"{problem.subjects[x].name}" if x in problem.subjects else x,
            help="Seleziona le materie che svolgono lezione in quest'aula.",
            key=f"room_subjs_fld{r_key_suffix}"
        )
    with c_r4:
        init_teachers = [t for t in getattr(target_r, "teacher_ids", []) if t in problem.teachers] if is_editing_room else []
        r_teachers_choice = st.multiselect(
            "👨‍🏫 Assegna a Docenti Specifici (100% Garantita):",
            options=list(problem.teachers.keys()),
            default=init_teachers,
            format_func=lambda x: f"{problem.teachers[x].name} ({get_teacher_subjects_display(problem.teachers[x], problem)})" if x in problem.teachers else x,
            help="Assegna quest'aula specificamente a uno o più docenti.",
            key=f"room_teachers_fld{r_key_suffix}"
        )

    col_btn_r1, col_btn_r2 = st.columns([2, 1])
    with col_btn_r1:
        btn_r_label = "💾 Salva Modifiche Aula" if is_editing_room else "➕ Aggiungi Aula"
        if st.button(btn_r_label, type="primary", use_container_width=True, key=f"save_room_btn{r_key_suffix}"):
            if not r_id_input:
                st.warning("Inserisci l'ID identificativo dell'aula.")
            elif not r_name_input:
                st.warning("Inserisci il nome dell'aula.")
            else:
                is_lab_flag = (r_type_choice == "Laboratorio Speciale / Palestra / Spazio Esclusivo")
                problem.rooms[r_id_input] = Classroom(
                    id=r_id_input,
                    name=r_name_input,
                    subject_ids=r_subjs_choice,
                    teacher_ids=r_teachers_choice,
                    capacity=r_cap_input,
                    is_special_lab=is_lab_flag,
                    priority=r_prio_input
                )
                st.session_state.editing_room_id = None
                st.success(f"Aula '{r_name_input}' salvata con successo!")
                st.rerun()

    with col_btn_r2:
        if is_editing_room:
            if st.button("❌ Chiudi / Annulla", use_container_width=True, key=f"cancel_room_btn{r_key_suffix}"):
                st.session_state.editing_room_id = None
                st.rerun()

def render_room_bottlenecks_resolver(problem: TimetableProblem, key_suffix: str = ""):
    """Rileva e visualizza un assistente interattivo per la risoluzione dei colli di bottiglia su aule/laboratori,
    proponendo di lavorare a classi aperte (chiedendo quali classi) oppure di dedicare un secondo spazio."""
    bottlenecks = get_room_bottlenecks(problem)
    if not bottlenecks:
        return
    
    tot_slots = problem.config.total_weekly_slots
    
    st.markdown("---")
    st.markdown("### 💡 **Risoluzione Guidata: Colli di Bottiglia & Sovraffollamento Spazi**")
    st.caption("Il sistema ha rilevato che le ore richieste per uno o più spazi superano la capienza massima disponibile. Scegli come risolvere per ciascun laboratorio:")
    
    for idx, b in enumerate(bottlenecks):
        r_name = b["room_name"]
        p_id = b["primary_room_id"]
        req_h = b["required_hours"]
        avail_h = b["available_hours"]
        excess_h = b["excess_hours"]
        cur_cap = b["current_capacity"]
        involved_classes = sorted(b["class_ids"])
        involved_teachers = [problem.teachers[t].name for t in b["teacher_ids"] if t in problem.teachers]
        
        card_key = f"b_card_{p_id}_{key_suffix}_{idx}"
        
        st.error(
            f"🚨 **Spazio Saturo**: **{r_name}**\n\n"
            f"- 📊 **Ore richieste**: **{req_h}h settimanali**\n"
            f"- 🏢 **Capienza massima disponibile**: **{avail_h}h** (Capienza: {cur_cap} {'classe' if cur_cap == 1 else 'classi'} in contemporanea per {tot_slots} ore)\n"
            f"- ⚠️ **Ore in eccesso / Collo di bottiglia**: **+{excess_h}h in soprannumero**\n"
            f"- 👨‍🏫 **Docenti interessati**: {', '.join(involved_teachers) if involved_teachers else 'Docenti della disciplina'}"
        )
        
        with st.container():
            col_opt1, col_opt2 = st.columns(2)
            
            with col_opt1:
                st.markdown(
                    """
                    <div style="background: #f0fdf4; border: 1.5px solid #22c55e; border-radius: 10px; padding: 14px; margin-bottom: 10px;">
                        <div style="font-weight: 700; color: #15803d; font-size: 1.05rem;">👥 Opzione 1: Lavora a Classi Aperte</div>
                        <div style="font-size: 0.88rem; color: #166534; margin-top: 4px;">
                            Consenti a 2 o più classi di condividere contemporaneamente questo spazio / laboratorio (attività congiunta o compresenza a classi aperte).
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                sel_open_classes = st.multiselect(
                    f"Quali classi lavoreranno a classi aperte in '{r_name}'?",
                    options=involved_classes,
                    default=involved_classes,
                    format_func=lambda cid: f"Classe {problem.classes[cid].name}" if cid in problem.classes else cid,
                    key=f"ms_open_classes_{card_key}",
                    help="Seleziona le classi autorizzate a utilizzare lo spazio in contemporanea."
                )
                
                new_cap = st.number_input(
                    "Capienza contemporanea dello spazio (N° Classi insieme):",
                    min_value=2,
                    max_value=5,
                    value=max(2, cur_cap + 1),
                    key=f"num_open_cap_{card_key}",
                    help="Imposta a 2 (o più) per consentire la compresenza di classi aperte."
                )
                
                if st.button(
                    f"👥 Applica: Lavora a Classi Aperte (Capienza {new_cap})",
                    key=f"btn_apply_open_{card_key}",
                    type="primary",
                    use_container_width=True
                ):
                    if p_id in problem.rooms:
                        problem.rooms[p_id].capacity = new_cap
                    for other_r_id in b["room_ids"]:
                        if other_r_id in problem.rooms:
                            problem.rooms[other_r_id].capacity = new_cap
                    st.session_state["result"] = None
                    cl_names = ", ".join(problem.classes[c].name for c in sel_open_classes if c in problem.classes)
                    st.success(f"✅ Impostata capienza = {new_cap} per '{r_name}'! Le classi ({cl_names}) possono ora lavorare a classi aperte. Capienza totale: {new_cap * tot_slots}h settimanali.")
                    st.rerun()
                    
            with col_opt2:
                st.markdown(
                    """
                    <div style="background: #eff6ff; border: 1.5px solid #3b82f6; border-radius: 10px; padding: 14px; margin-bottom: 10px;">
                        <div style="font-weight: 700; color: #1d4ed8; font-size: 1.05rem;">🏢 Opzione 2: Dedica un Secondo Spazio</div>
                        <div style="font-size: 0.88rem; color: #1e40af; margin-top: 4px;">
                            Aggiungi un secondo laboratorio o aula polivalente di riserva da dedicare a questa materia per assorbire le ore eccedenti.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                default_name = r_name
                if "(Principale)" in default_name:
                    default_name = default_name.replace("(Principale)", "(Secondario / Riserva)")
                elif not default_name.endswith("2"):
                    default_name = f"{default_name} (Secondo Spazio / Riserva)"
                else:
                    default_name = f"{default_name}_Bis"
                    
                new_room_name_val = st.text_input(
                    "Nome del Secondo Spazio da Dedicare:",
                    value=default_name,
                    key=f"txt_sec_room_name_{card_key}"
                )
                
                sec_prio_val = st.selectbox(
                    "Priorità di Assegnazione:",
                    options=[2, 1],
                    format_func=lambda p: "🥈 Priorità 2 (Secondario / Riserva per overflow)" if p == 2 else "🥇 Priorità 1 (Pari merito con il principale)",
                    key=f"sb_sec_prio_{card_key}"
                )
                
                if st.button(
                    "➕ Crea & Dedica Secondo Spazio",
                    key=f"btn_create_sec_{card_key}",
                    type="primary",
                    use_container_width=True
                ):
                    orig_r = problem.rooms.get(p_id)
                    new_id = f"{p_id}_secondario"
                    counter = 2
                    while new_id in problem.rooms:
                        new_id = f"{p_id}_secondario_{counter}"
                        counter += 1
                        
                    sub_ids = list(orig_r.subject_ids) if orig_r else b["subject_ids"]
                    t_ids = list(getattr(orig_r, "teacher_ids", [])) if orig_r else b["teacher_ids"]
                    is_lab = orig_r.is_special_lab if orig_r else True
                    
                    problem.rooms[new_id] = Classroom(
                        id=new_id,
                        name=new_room_name_val,
                        subject_ids=sub_ids,
                        teacher_ids=t_ids,
                        capacity=1,
                        is_special_lab=is_lab,
                        priority=sec_prio_val
                    )
                    st.session_state["result"] = None
                    st.success(f"✅ Creato con successo lo spazio '{new_room_name_val}'! La disponibilità complessiva è salita a {(cur_cap + 1) * tot_slots}h settimanali.")
                    st.rerun()
        st.markdown("---")

# =============================================================
# GESTIONE SIDEBAR & SCENARI
# =============================================================
def compute_active_scenario(prob: TimetableProblem) -> str:
    if not prob.teachers and not prob.classes:
        return "empty"
    if bool(getattr(prob.config, "has_musical_curriculum", False)) or any(getattr(c, "curriculum_type", "") == "musicale" for c in prob.classes.values()):
        return "musical"
    if any(getattr(c, "curriculum_type", "") == "prolungato" for c in prob.classes.values()):
        return "prolungato"
    if getattr(prob.config, "num_days", 5) == 6:
        return "standard_6d"
    if prob.config.is_dada:
        has_theater = (
            getattr(prob.config, "approfondimento_type", "") == "custom_activity"
            or getattr(prob.config, "approfondimento_subject", "") == "tea"
            or any(a.subject_id == "tea" for a in prob.assignments)
            or "teatro" in prob.rooms
        )
        return "dada_theater" if has_theater else "dada"
    return "standard"

active_scen = compute_active_scenario(problem)
if "dada_model_active_toggle" not in st.session_state:
    st.session_state["dada_model_active_toggle"] = bool(problem.config.is_dada)

# SIDEBAR LATERALE
with st.sidebar:
    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 2px;">
        <span style="font-size: 1.35rem; font-weight: 800; color: #1e3a8a;">🏫 Orario Scolastico</span>
        <span style="background: #2563eb; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.76rem; font-weight: 700;">{APP_VERSION}</span>
    </div>
    """, unsafe_allow_html=True)
    st.caption(f"Motore di Ottimizzazione CP-SAT OR-Tools · Build **{APP_VERSION}**")
    st.markdown("---")
    
    st.markdown("### 🎛️ **Scenari & Dati Demo**")
    st.caption("Carica uno scenario demo completo di 18 classi e docenti:")
    
    is_std_act = (active_scen == "standard")
    if st.button(f"{'✅ ' if is_std_act else ''}🔄 Standard (5 Giorni - 18 cl.)", type="primary" if is_std_act else "secondary", use_container_width=True, help="Carica scenario demo tradizionale su 5 giorni (Lun-Ven, 6 ore/giorno) per 18 classi con aule ordinarie"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        st.session_state["dada_model_active_toggle"] = False
        st.session_state.result = None
        st.rerun()

    is_std6_act = (active_scen == "standard_6d")
    if st.button(f"{'✅ ' if is_std6_act else ''}📅 Settimana 6 Giorni (18 cl. + Giorno Libero)", type="primary" if is_std6_act else "secondary", use_container_width=True, help="Carica scenario demo su 6 giorni (Lun-Sab, 5 ore/giorno) con giorno libero preferito assegnato a ciascun docente"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=6, with_musical_curriculum=False, with_extended_curriculum=False)
        st.session_state["dada_model_active_toggle"] = False
        st.session_state.result = None
        st.rerun()

    is_dada_act = (active_scen == "dada")
    if st.button(f"{'✅ ' if is_dada_act else ''}🏫 Modello DADA (18 cl.)", type="primary" if is_dada_act else "secondary", use_container_width=True, help="Carica scenario demo DADA standard con aule disciplinari"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        st.session_state["dada_model_active_toggle"] = True
        st.session_state.result = None
        st.rerun()

    is_tea_act = (active_scen == "dada_theater")
    if st.button(f"{'✅ ' if is_tea_act else ''}🎭 DADA + Teatro (18 cl.)", type="primary" if is_tea_act else "secondary", use_container_width=True, help="Carica scenario demo DADA con Laboratorio Teatro attivo"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=True, with_theater=True, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        st.session_state["dada_model_active_toggle"] = True
        st.session_state.result = None
        st.rerun()

    is_mus_act = (active_scen == "musical")
    if st.button(f"{'✅ ' if is_mus_act else ''}🎼 Tempo Musicale (32h - Corso F)", type="primary" if is_mus_act else "secondary", use_container_width=True, help="Carica scenario Tradizionale (NO DADA) con Indirizzo Musicale (Corso F a 32h con Orchestra/Solfeggio e 4 docenti di strumento in compresenza)"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=True, with_extended_curriculum=False)
        st.session_state["dada_model_active_toggle"] = False
        st.session_state.result = None
        st.rerun()

    is_ext_act = (active_scen == "prolungato")
    if st.button(f"{'✅ ' if is_ext_act else ''}🕒 Tempo Prolungato (36h - Corso E)", type="primary" if is_ext_act else "secondary", use_container_width=True, help="Carica scenario Tradizionale (NO DADA) con Tempo Prolungato (Corso E a 36h con rientri pomeridiani e compresenze)"):
        st.session_state.clear()
        st.session_state.problem = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=True)
        st.session_state["dada_model_active_toggle"] = False
        st.session_state.result = None
        st.rerun()

    st.markdown("---")
    st.markdown("### 🗑️ **Nuovo Orario da Zero**")
    st.caption("Azzera tutti i docenti, classi, aule e cattedre per compilare l'orario della tua scuola da zero:")
    
    is_empty_act = (active_scen == "empty")
    if st.button(f"{'✅ ' if is_empty_act else ''}🗑️ Resetta Tutto (Database Vuoto)", type="primary" if is_empty_act else "secondary", use_container_width=True, help="Cancella tutti i dati demo e lascia il database vuoto"):
        st.session_state.clear()
        st.session_state.problem = get_empty_problem()
        st.session_state["dada_model_active_toggle"] = False
        st.session_state.result = None
        st.rerun()

    st.markdown("---")
    st.markdown("### 📊 **Stato Organico Attuale**")
    tot_t_cnt = len(problem.teachers)
    tot_c_cnt = len(problem.classes)
    tot_h_cnt = sum(a.hours_per_week for a in problem.assignments)
    tot_r_cnt = len(problem.rooms)
    
    st.markdown(f"- 👨‍🏫 **Docenti**: `{tot_t_cnt}`")
    st.markdown(f"- 🏫 **Classi**: `{tot_c_cnt}`")
    st.markdown(f"- 📚 **Ore Cattedra**: `{tot_h_cnt}h`")
    st.markdown(f"- 🏢 **Aule / Lab**: `{tot_r_cnt}`")

    if is_empty_act:
        st.info("ℹ️ **Database Vuoto**: 0 docenti e 0 classi. Pronto per l'inserimento manuale nei Tab 1, 2, 3 o l'importazione Excel.")
    elif is_std6_act:
        st.success("📅 **Settimana 6 Giorni (Lun-Sab) Caricata**: Giorno libero individuale impostato per tutti i docenti!")
    elif is_tea_act:
        st.success("🎭 **DADA + Teatro Caricato**")
    elif is_dada_act:
        st.success("🏫 **DADA Standard Caricato**")
    elif is_std_act:
        st.success("🔄 **Standard Tradizionale (5 Giorni) Caricato**")

    st.markdown("---")
    with st.expander("📖 **Manuale d'Uso Operativo (Guida Clic-per-Clic)**", expanded=False):
        st.markdown("""
# 📖 Manuale d'Uso: Guida Operativa Clic-per-Clic

---

## 🎛️ 1. BARRA LATERALE (SIDEBAR) – SCENARI & RESET

- **Pulsante `🔄 Standard (5 Giorni - 18 cl.)`**: 
  - *Cosa fa*: Cancella l'orario in memoria e carica lo scenario demo ministeriale su 5 giorni (Lunedì–Venerdì, 6 ore/giorno) per 18 classi con aule ordinarie.
- **Pulsante `📅 Settimana 6 Giorni (18 cl. + Giorno Libero)`**: 
  - *Cosa fa*: Carica lo scenario su 6 giorni (Lunedì–Sabato, 5 ore/giorno) pre-assegnando a ogni docente un giorno libero individuale preferito.
- **Pulsante `🏫 Modello DADA (18 cl.)`**: 
  - *Cosa fa*: Carica lo scenario con le 26 aule disciplinari tematiche DADA e docenti assegnati ai rispettivi laboratori.
- **Pulsante `🎭 DADA + Teatro (18 cl.)`**: 
  - *Cosa fa*: Carica lo scenario DADA comprensivo del laboratorio teatrale e spazi polivalenti.
- **Pulsante `🗑️ Resetta Tutto (Database Vuoto)`**: 
  - *Cosa fa*: Cancella all'istante tutti i docenti, classi, aule e cattedre, lasciando il database a 0 per inserire da zero i dati della propria scuola o importare un file Excel.
- **Riquadro `📊 Stato Organico Attuale`**:
  - Mostra i contatori in tempo reale di Docenti registrati, Classi, Ore totali di cattedra e Aule configurate.

---

## ⚙️ 2. SCHEDA 1 – STRUTTURA SCOLASTICA & TEMPI

### A. Sezione Importazione & Modelli Offline
- **Pulsante `📊 Scarica Modello Excel (.xlsx) Vuoto`**: Scarica sul computer un file Excel già formattato con le intestazioni standard (Docenti, Cattedre, Vincoli) da compilare offline.
- **Pulsante `📄 Scarica Modello CSV Vuoto`**: Scarica lo stesso template in formato CSV (UTF-8 con BOM).
- **Pulsante `📊 Esporta Dati Attuali in Excel (.xlsx)`**: Esporta tutti i dati attualmente presenti a schermo in un file Excel.
- **File Uploader `📂 Trascina o seleziona il file compilato`**: Trascina il file compilato (.xlsx o .csv) per importare in un solo clic l'intero organico scolastico.

### B. Parametri Scuola & Giorni
- **Campo `Nome Istituto Comprensivo`**: Inserisci il nome della scuola (comparirà nelle intestazioni di tutte le stampe, PDF ed Excel).
- **Radio `Articolazione Settimanale (5 o 6 Giorni)`**:
  - Clic su `5 Giorni`: Imposta la settimana corta (Lun–Ven) e allinea automaticamente a 6 ore al giorno (30h totali).
  - Clic su `6 Giorni`: Imposta la settimana lunga (Lun–Sab) e allinea a 5 ore al giorno (30h totali).
- **Campo `Numero Totale Classi`**: Imposta il numero di classi (es. 18).
  - Pulsante `➕ Crea Struttura Classi`: Genera in automatico le classi distribuite sulle sezioni A, B, C... da 1ª a 3ª media.
  - Pulsante `🔄 Rigenera a N Classi`: Riadatta l'organico al nuovo numero ripulendo eventuali cattedre orfane.

### C. Modello DADA & Blocchi da 2 Ore
- **Interruttore `Attiva Modello DADA`**: Attiva la rotazione degli studenti nelle aule tematiche.
- **Opzione `Politica Blocchi DADA`**:
  - `🟢 Tolleranza Flessibile (Consigliato)`: Il solutore piazza i blocchi da 2 ore dove è più efficiente (anche 2ª-3ª o 4ª-5ª), riducendo al minimo le ore buche dei docenti.
  - `🔒 Blocchi Rigidi Allineati (1-2, 3-4, 5-6)`: Forza i blocchi solo su ore pari/dispari per limitare gli spostamenti nei corridoi solo durante gli intervalli.

### D. Ore Giornaliere (Selettori Numerici)
- **Selettori compatti con freccette (▲ / ▼)** per ciascun giorno: Aumenta o diminuisce le ore di quel giorno da 1 a 9.
- **Pulsante `⚡ Tutte a 5h`**: Forza tutti i giorni a 5 ore.
- **Pulsante `⚡ Tutte a 6h`**: Forza tutti i giorni a 6 ore.

### E. Seconda Lingua Comunitaria (2h)
- **Menu a tendina**: Scegli tra Spagnolo, Francese, Tedesco o Personalizzata (adegua automaticamente le 2h per classe previste dal DPR 89/2009).

---

## 👥 3. SCHEDA 2 – CORPO DOCENTI & REGOLE DI SERVIZIO

### A. Inserimento & Modifica Docente
- **Pulsante / Expander `➕ Nuovo Docente`**: Apre il form di creazione.
- **Campo `Nome e Cognome`**: Inserisci il nome del docente (es. *Prof.ssa Rossi M.*).
- **Menu `Classe di Concorso (CDC)`**: Seleziona la materia ministeriale (A-22 Lettere, A-28 Matematica/Scienze, A-25 Inglese, A-49 Motoria, ecc.).
- **Spunta `Docente Part-Time`**: 
  - Se attivata, compaiono i campi *Ore Contrattuali* e *Max Giorni Lavorativi a Settimana* (vincolo rigido: il solutore non supererà mai quel numero di giorni di presenza).
- **Menu `1° e 2° Giorno Libero Preferito`**: Seleziona i giorni di riposo desiderati.
- **Spunte `Preferisce Entrata Posticipata` / `Preferisce Uscita Anticipata`**: Indica le fasce orarie gradite.
- **Griglia `Indisponibilità Assoluta (Blocco Rigido)`**: Clicca sulle caselle orarie della matrice: le celle rosse diventano interdette al 100% e il solutore non assegnerà mai lezioni in quegli slot.
- **Pulsante `💾 Salva Docente`**: Salva la scheda docente nel database.

### B. Gestione Docenti Esistenti
- **Pulsante `✏️ Modifica` su ciascuna card**: Apre il pannello di modifica evidenziato in blu con i dati precompilati per aggiornare desiderata o cattedre.
- **Pulsante `🗑️ Elimina`**: Cancella il docente e rimuove le sue assegnazioni.
- **Expander `🗑️ Gestione Multipla`**: Spunta più docenti e clicca `🗑️ Elimina Selezionati` per rimuoverli in blocco.

### C. Regole di Servizio Ministeriali Rigide Garantite
Il solutore rispetta automaticamente 4 regole categoriche per tutti i docenti:
1. *Minimo 2 ore al giorno* (mai 1 sola ora isolata).
2. *Massimo 4 ore consecutive* senza pause.
3. *Massimo 5 ore al giorno solo se interrotte da almeno 1 ora di buca/pausa*.
4. *Tetto massimo ore buche settimanali* impostato nella scheda.

---

## 🏫 4. SCHEDA 3 – CLASSI, AULE DADA & CLASSI APERTE

### A. Quadro Orario Classi & Assegnazione Cattedre
- Per ogni classe è presente la tabella delle discipline a 30 ore:
  - *Italiano (6h)*, *Storia (2h)*, *Geografia (2h)*, *Matematica (4h)*, *Scienze (2h)*, *Inglese (3h)*, *2ª Lingua (2h)*, *Tecnologia (2h)*, *Arte (2h)*, *Musica (2h)*, *Motoria (2h)*, *Religione (1h)*, *Approfondimento (1h)*.
- **Menu a tendina Docente**: Assegna l'insegnante per ciascuna materia.
- **Spunta `🔗 Forza Blocco 2 Ore`**: Vincola la materia a svolgersi in un blocco consecutivo da 2 ore.
- **Regola No 3 Ore di Fila**: Il solutore limita d'ufficio le materie a max 2 ore al giorno per classe (es. Italiano 6h viene distribuito in 3 giorni da 2h ciascuno, impedendo 3 o 4 ore di fila).

### B. Ora di Approfondimento & Potenziamento (1h)
- 1 ora settimanale per classe per completare il quadro a 30h:
  - *In Lettere (A-22)*: Potenziamento linguistico, scrittura o metodo di studio.
  - *Scientifico / STEM / Digitale*: Laboratori di coding e robotica in aula *R2-D2*.
  - *Laboratorio Teatrale / Espressivo*: Attività in *Auditorium*.

### C. Gruppi di Classi Aperte & Parallelismi Didattici
- **Pulsante `➕ Nuovo Gruppo Classi Aperte`**:
  - *Materia*: Scegli la disciplina da sincronizzare (es. *Scienze Motorie, Approfondimento, Lingue*).
  - *Classi Coinvolte*: Seleziona 2 o più classi (es. *1A, 1B, 1C*).
  - *Ore in Parallelo*: Numero di ore sincronizzate (1h o 2h).
  - *Spazio Condiviso*: Assegna un'aula polivalente o palestra (es. *Auditorium, Bebe Vio*).
  - **Due modalità automatiche**:
    - *Docenti Distinti*: Le classi fanno lezione allo stesso momento con docenti diversi.
    - *Docente Unico Accorpato*: Se lo stesso docente è assegnato a tutte le classi del gruppo, le lezioni vengono fuse in un'unica sessione comune nello spazio condiviso.

### D. Rete 26 Aule DADA & Priorità Spazi
- **Priorità 1 vs 2**: 
  - *BEBE VIO (Priorità 1 - Principale)*: Viene saturata per prima fino a 30h.
  - *PALESTRA MURATO (Priorità 2 - Riserva)*: Riceve solo il residuo e le lezioni contemporanee.
- **Continuità Atomica 2 Ore**: Entrambe le ore di ogni blocco doppio si svolgono **sempre nella stessa identica aula/palestra**.

---

## ♿ 5. SCHEDA 4 – SOSTEGNO DIDATTICO & STUDENTI DVA

- **Pulsante `➕ Aggiungi Studente DVA`**: Inserisci nome alunno, classe e monte ore settimanale da PEI.
- **Assegnazione Docente di Sostegno**: Associa il docente all'alunno.
- **Aree Disciplinari Preferite**: Seleziona le materie (Umanistica, Scientifica, Espressiva) su cui concentrare la compresenza.
- **Pulsante `🚀 Genera Orario Sostegno`**: Incastra le ore di sostegno in compresenza con i docenti curricolari scelti, distribuendole equamente ed evitando buchi per l'insegnante di sostegno.

---

## 🚀 6. SCHEDA 6 – GENERATORE ORARIO (SOLUTORE CP-SAT)

- **Slider `Tempo Massimo di Calcolo (Secondi)`**: Imposta 35-60 secondi.
- **Campo `Seme Casuale (Random Seed)`**: Modificando questo intero (es. 42, 100, 777), il solutore esplora percorsi alternativi generando varianti orarie diverse a parità di vincoli.
- **Pulsante `🚀 GENERA ORARIO SCOLASTICO`**:
  - Avvia il solutore a 2 fasi:
    - *Fase 1 (SAT)*: Soddisfa il 100% dei vincoli rigidi (cattedre, compresenze, capienze).
    - *Fase 2 (Warm-Start)*: Ottimizza e comprime le ore buche, assegna i giorni liberi e i desiderata.
  - Al termine mostra il report con lo stato (**FEASIBLE / OPTIMAL**), il tempo impiegato e il bilancio buche.

---

## 📅 7. SCHEDA 7 – VISTE ORARIO & ESPORTAZIONI

### A. Le 5 Viste a Schermo
- **Menu a tendina `Seleziona Tipologia Vista`**:
  1. `🏫 Per Classe`: Orario con discipline, docenti, badge aula DADA e compresenze.
  2. `👤 Per Docente Curricolare`: Quadro settimanale con classi, aule e badge `☕ ORA BUCA`.
  3. `♿ Per Docente di Sostegno`: Dettaglio con badge studente, materia curricolare in corso e docente affiancato.
  4. `🏫 Classe con Sostegni Integrati`: Tabellone completo della classe con docenti curricolari + badge viola di tutti i docenti di sostegno compresenti.
  5. `🏛️ Per Aula / Spazio DADA`: Tabellone di occupazione dei 26 spazi con le classi ospitate ora per ora.

### B. Pulsanti di Download Esportazioni
- **Pulsante `📄 Scarica PDF Orario Classi`**: Genera il PDF multipagina vettoriale impaginato con tutte le classi.
- **Pulsante `📄 Scarica PDF Orario Docenti`**: Genera il PDF con tutti gli orari dei docenti.
- **Pulsante `📄 Scarica PDF Orario Sostegno`**: Genera il PDF dedicato agli insegnanti di sostegno.
- **Pulsante `📊 Scarica Tabellone Generale Excel (.xlsx)`**: Scarica il file Excel con **tabellone unificato (un docente per riga, curricolari + sostegno)** con tutte le ore della settimana per la gestione di presenze e supplenze.
        """)

    # Dialogo Novità Versione v1.1.0
    if hasattr(st, "dialog"):
        @st.dialog(f"✨ Novità della Versione {APP_VERSION}")
        def show_whats_new_dialog():
            st.markdown("""
### 🚀 Nuove Funzionalità & Miglioramenti Chiave

1. **✏️ Ritocchi Manuali & Smart Swap (Scheda 6)**:
   - Spostamento atomico manuale o scambio tra due ore con controllo conflitti semaforico istantaneo (🟢 Valido / 🔴 Conflitto).
   - **Assistente Smart Repair**: calcola automaticamente la catena minima di spostamenti a cascata (1-3 mosse) per risolvere il conflitto senza rompere i vincoli scolastici.
   - Pulsante **"↩️ Annulla Ultima Modifica"** per il ripristino istantaneo dello stato precedente.

2. **📥 Importazione Orario da Excel con Audit Conflitti**:
   - Carica un orario compilato o ritoccato a mano in formato `.xlsx`.
   - **Audit automatico immediato** che rileva sovrapposizioni docenti, aule sature, ore per materia mancanti o in eccesso.
   - Promozione a *"Orario Curricolare Ufficiale"* su cui incastrare il sostegno.

3. **♿ Generatore Sostegno & Compresenze Prioritarie**:
   - Barra di avanzamento in tempo reale per la generazione del sostegno.
   - Algoritmo di massimizzazione delle doppie coperture e rispetto rigoroso delle preferenze PEI.

4. **🔒 Anonimizzazione Completa & Organico Certificato**:
   - Nomi dei docenti di fantasia realistici ed eleganti, nel rispetto del 100% dell'organico e cattedre ministeriali.
            """)
            if st.button("👍 Ho Capito", type="primary", use_container_width=True):
                st.rerun()

        if st.button(f"✨ Novità Versione {APP_VERSION}", use_container_width=True):
            show_whats_new_dialog()

    st.caption(f"📌 **Orario Scolastico Facile** · Release `{APP_VERSION}` · [GitHub](https://github.com/Anisanimus/orario-scolastico)")

tabs = st.tabs([
    "⚙️ 1. Struttura & Indirizzi",
    "👥 2. Docenti, Spazi & Aule",
    "🔗 3. Blocchi 2h/3h & Paralleli",
    "♿ 4. Sostegno & DVA",
    "🚀 5. Genera Orario",
    "📅 6. Visualizza Orario & Export"
])

# =============================================================
# TAB 1: CONFIGURAZIONE STRUTTURA SCOLASTICA E INDIRIZZI
# =============================================================
with tabs[0]:
    st.header("⚙️ Configurazione Struttura Scolastica & Indirizzi")
    
    with st.expander("📁 Gestione Dati Completa Scuola & Backup Master (.xlsx)", expanded=False):
        st.write("Scarica o ricarica l'intera banca dati della scuola (**Struttura, Docenti, Classi, Aule DADA, Cattedre, Sostegno, Parallelismi**) in un **unico file Excel multi-foglio**:")
        c_csv_d1, c_csv_d2 = st.columns(2)
        with c_csv_d1:
            st.markdown("##### 📥 Esporta / Scarica Backup")
            st.download_button(
                "📥 Scarica Backup Completo Scuola (.xlsx)",
                data=generate_unified_school_excel(problem),
                file_name=f"Backup_Scuola_Completo_{problem.config.school_name.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="tab1_dl_master_xlsx",
                use_container_width=True,
                help="Scarica un unico file Excel (.xlsx) contenente tutti i fogli della scuola: docenti, classi, aule, cattedre, sostegno e parallelismi."
            )
            st.download_button(
                "📊 Scarica Modello Vuoto Multi-Foglio (.xlsx)",
                data=generate_unified_school_excel(None),
                file_name="Modello_Master_Scuola_Vuoto.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="tab1_dl_empty_master_xlsx",
                use_container_width=True,
                help="Scarica il modello Excel vuoto formattato su 7 fogli pronto per la compilazione offline."
            )
        with c_csv_d2:
            st.markdown("##### 📤 Ripristina / Carica Backup")
            up_file_tab1 = st.file_uploader("📂 Trascina o seleziona il file (.xlsx o .csv)", type=["xlsx", "csv"], key="tab1_file_up")
            if up_file_tab1 is not None:
                file_sig = f"{up_file_tab1.name}_{up_file_tab1.size}"
                if st.session_state.get("processed_tab1_file") != file_sig:
                    try:
                        fname = up_file_tab1.name.lower()
                        if fname.endswith(".xlsx"):
                            parsed_prob, logs = parse_unified_school_excel(up_file_tab1.getvalue(), problem.config)
                        else:
                            content_str = up_file_tab1.getvalue().decode('utf-8-sig', errors='replace')
                            parsed_prob, logs = parse_csv_timetable(content_str, problem.config)
                        st.session_state["problem"] = parsed_prob
                        st.session_state["result"] = None
                        st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1
                        st.session_state["processed_tab1_file"] = file_sig
                        st.session_state["tab1_upload_logs"] = logs
                        st.session_state["tab1_upload_success"] = True
                        st.rerun()
                    except Exception as e:
                        st.error(f"Errore durante l'elaborazione del file: {e}")

            if st.session_state.get("tab1_upload_success") and st.session_state.get("tab1_upload_logs"):
                st.success("🎉 Database scuola importato con successo!")
                for log_msg in st.session_state.get("tab1_upload_logs", []):
                    st.info(log_msg)

    v = st.session_state.get("data_version", 0)
    col1, col2, col3 = st.columns([2, 1.2, 1])
    with col1:
        problem.config.school_name = st.text_input(
            "Nome Istituto Comprensivo / Scuola Media",
            value=problem.config.school_name,
            key=f"school_name_txt_{v}"
        )
    with col2:
        def on_num_days_changed():
            new_days = st.session_state.get(f"sel_num_days_radio_{v}", problem.config.num_days)
            if new_days != problem.config.num_days:
                problem.config.num_days = new_days
                if new_days == 6:
                    problem.config.daily_hours = [5, 5, 5, 5, 5, 5]
                    for i in range(6): st.session_state[f"dh_{i}"] = 5
                else:
                    problem.config.daily_hours = [6, 6, 6, 6, 6]
                    for i in range(5): st.session_state[f"dh_{i}"] = 6
                st.session_state["result"] = None

        num_days = st.radio(
            "Articolazione Settimanale",
            [5, 6],
            index=0 if problem.config.num_days == 5 else 1,
            key=f"sel_num_days_radio_{v}",
            on_change=on_num_days_changed,
            format_func=lambda x: f"{x} Giorni ({'Settimana Corta Lun-Ven: 6h/dì' if x==5 else 'Settimana Lunga Lun-Sab: 5h/dì'})",
            horizontal=True
        )
        problem.config.num_days = num_days

    with col3:
        cur_cl_count = len(problem.classes) if problem.classes else 18
        target_num_classes = st.number_input(
            "Numero Totale Classi:",
            min_value=1,
            max_value=45,
            value=cur_cl_count,
            step=1,
            help="Numero di classi della scuola (es. 18 classi = 6 sezioni A..F da 1ª a 3ª media)."
        )

    # -------------------------------------------------------------
    # 1. SCANSIONE ORARIA ANTIMERIDIANA BASE (30h)
    # -------------------------------------------------------------
    with st.container(border=True):
        st.markdown("##### 📅 Scansione Oraria Settimanale Base (Tempo Normale - 30h)")
        cols_days = st.columns(num_days)
        new_daily_hours = list(problem.config.daily_hours[:num_days])
        while len(new_daily_hours) < num_days:
            new_daily_hours.append(5 if num_days == 6 else 6)

        updated_hours = []
        has_changed = False
        for d_i in range(num_days):
            with cols_days[d_i]:
                val = st.number_input(
                    label=f"**{DAYS_OF_WEEK[d_i]}**",
                    min_value=1,
                    max_value=9,
                    value=int(new_daily_hours[d_i]),
                    step=1,
                    key=f"dh_num_input_{d_i}",
                    help=f"Ore di lezione di {DAYS_OF_WEEK[d_i]}"
                )
                updated_hours.append(int(val))
                if int(val) != new_daily_hours[d_i]:
                    has_changed = True

        if has_changed:
            problem.config.daily_hours = updated_hours
            st.session_state.result = None
            st.rerun()

    # -------------------------------------------------------------
    # 2. ACCORDION 1: MODELLO DADA
    # -------------------------------------------------------------
    with st.expander(f"🏫 Modello Didattico DADA (Aule per Disciplina) {'🟢 [ATTIVO]' if getattr(problem.config, 'is_dada', False) else '⚪ [DISATTIVATO]'}", expanded=bool(getattr(problem.config, "is_dada", False))):
        dada_toggle_key = "dada_model_active_toggle"
        if dada_toggle_key not in st.session_state:
            st.session_state[dada_toggle_key] = bool(problem.config.is_dada)

        def on_dada_toggle_change():
            problem.config.is_dada = st.session_state[dada_toggle_key]
            st.session_state.result = None

        st.toggle(
            "Attiva Modello DADA (Aule assegnate ai Dipartimenti / Discipline)",
            key=dada_toggle_key,
            on_change=on_dada_toggle_change,
            help="Nel modello DADA ogni aula è dedicata a una materia e gli studenti si spostano tra le aule."
        )

        if problem.config.is_dada:
            st.markdown("##### 🚶‍♂️ Politica Spostamento Studenti & Allineamento Blocchi DADA")
            dada_strategy = st.radio(
                "Come desideri posizionare i blocchi da 2 ore nelle aule DADA?",
                [
                    "🟢 Tolleranza Flessibile (Blocchi 2h liberi - Ottimizza al massimo le ore buche dei docenti)",
                    "🔒 Blocchi Rigidi Allineati 1-2, 3-4, 5-6 (Cambio aula solo ad intervallo o ricreazione)"
                ],
                index=1 if getattr(problem.config, "dada_strict_even_pairs", False) else 0,
                key="dada_strict_pairs_radio"
            )
            is_strict_pairs = "Blocchi Rigidi" in dada_strategy
            if is_strict_pairs != getattr(problem.config, "dada_strict_even_pairs", False):
                problem.config.dada_strict_even_pairs = is_strict_pairs
                st.session_state.result = None
                st.rerun()

    # -------------------------------------------------------------
    # 3. ACCORDION 2: ORA DI APPROFONDIMENTO PTOF (1h DPR 89/2009)
    # -------------------------------------------------------------
    cur_app_type = getattr(problem.config, "approfondimento_type", "subject")
    app_label_status = "🟢 [ATTIVO]"
    with st.expander(f"🎯 Ora di Approfondimento PTOF (1h Quota Autonomia DPR 89/2009) {app_label_status}", expanded=False):
        c_lng1, c_lng2 = st.columns(2)
        with c_lng1:
            cur_second_lang = getattr(problem.config, "second_language", "Spagnolo")
            lang_list = ["Spagnolo", "Francese", "Tedesco", "Altra Lingua / Personalizzata"]
            default_l_idx = lang_list.index(cur_second_lang) if cur_second_lang in lang_list else 0
            sel_l_opt = st.selectbox(
                "Seconda Lingua Comunitaria (2h settimanali):",
                lang_list,
                index=default_l_idx,
                key=f"sel_lang_opt_{v}",
                help="Scegli la seconda lingua comunitaria insegnata nella scuola."
            )
            if sel_l_opt != getattr(problem.config, "second_language", ""):
                problem.config.second_language = sel_l_opt
                if "spa" in problem.subjects:
                    problem.subjects["spa"].name = f"Seconda Lingua ({sel_l_opt})"
                st.session_state.result = None

        app_type = st.radio(
            "Come viene utilizzata l'ora di Approfondimento nella tua scuola?",
            ["Potenziamento di una Materia Tradizionale (+1h)", "🎭 Attività / Laboratorio Dedicato (es. Teatro, Coding, Robotica)"],
            index=0 if cur_app_type == "subject" else 1,
            horizontal=True
        )

        if "Potenziamento" in app_type:
            problem.config.approfondimento_type = "subject"
            approfondimento_map = {
                "ita": "✍️ Italiano / Lettere (Italiano passa da 5h a 6h -> Totale Lettere 10h)",
                "mat": "📐 Matematica (Matematica passa da 4h a 5h -> Totale Mat/Sci 7h)",
                "sci": "🔬 Scienze Sperimentali (Scienze passa da 2h a 3h -> Totale Mat/Sci 7h)",
                "ing": "🇬🇧 Potenziamento Inglese (Inglese passa da 3h a 4h)",
                "tec": "💻 Tecnologia / Coding (Tecnologia passa da 2h a 3h)",
                "spa": "🇪🇸 Seconda Lingua Comunitaria (Spagnolo/Francese passa da 2h a 3h)"
            }
            curr_app = getattr(problem.config, "approfondimento_subject", "ita")
            chosen_app_key = st.selectbox(
                "Seleziona la disciplina da potenziare:",
                options=list(approfondimento_map.keys()),
                index=list(approfondimento_map.keys()).index(curr_app) if curr_app in approfondimento_map else 0,
                format_func=lambda k: approfondimento_map[k]
            )
            problem.config.approfondimento_subject = chosen_app_key
        else:
            problem.config.approfondimento_type = "custom_activity"
            c_app1, c_app2 = st.columns(2)
            with c_app1:
                custom_act_name = st.text_input("Nome Attività PTOF", value=getattr(problem.config, "approfondimento_custom_name", "Laboratorio di Teatro"))
                custom_room_name = st.text_input("Aula / Spazio Dedicato (opzionale)", value="Spazio Teatro (2 Aule)")
            with c_app2:
                cdc_options = [
                    "A-22 (Lettere - Italiano, Storia, Geografia)",
                    "A-28 (Matematica e Scienze)",
                    "A-24 (Lingue Straniere)",
                    "A-60 (Tecnologia)",
                    "A-30 (Musica)",
                    "A-01 (Arte e Immagine)"
                ]
                cur_cdc = getattr(problem.config, "approfondimento_cdc", "A-22")
                cdc_idx = next((i for i, opt in enumerate(cdc_options) if cur_cdc in opt), 0)
                chosen_cdc_label = st.selectbox("Classe di Concorso (CdC) Attribuita", cdc_options, index=cdc_idx)
                chosen_cdc_code = chosen_cdc_label.split(" ")[0]

            deduct_options = {
                "ita": "✍️ Togli a Italiano (Italiano passa da 6h a 5h + 1h Teatro -> Totale CdC Lettere resta 10h)",
                "sto": "📜 Togli a Storia (Storia passa da 2h a 1h + 1h Teatro -> Totale CdC Lettere resta 10h)",
                "geo": "🌍 Togli a Geografia (Geografia passa da 2h a 1h + 1h Teatro -> Totale CdC Lettere resta 10h)",
                "none": "➕ Nessuna (Ora aggiuntiva PTOF: Lettere fa 10h + 1h Teatro = 11h)"
            }
            cur_ded = getattr(problem.config, "approfondimento_deduct_from", "ita")
            ded_keys = list(deduct_options.keys())
            d_idx = ded_keys.index(cur_ded) if cur_ded in ded_keys else 0
            deduct_choice = st.radio(
                "Compensazione Oraria della CdC:",
                options=ded_keys,
                index=d_idx,
                format_func=lambda k: deduct_options[k]
            )

            problem.config.approfondimento_custom_name = custom_act_name
            problem.config.approfondimento_cdc = chosen_cdc_code
            problem.config.approfondimento_deduct_from = deduct_choice

    # -------------------------------------------------------------
    # 4. ACCORDION 3: INDIRIZZO MUSICALE (32h)
    # -------------------------------------------------------------
    has_mus_curr = bool(getattr(problem.config, "has_musical_curriculum", False))
    with st.expander(f"🎼 Indirizzo Musicale (32 Ore - con Rientro e Mensa) {'🟢 [ATTIVO]' if has_mus_curr else '⚪ [DISATTIVATO]'}", expanded=has_mus_curr):
        col_m_tog, col_m_info = st.columns([1.5, 2.5])
        with col_m_tog:
            has_mus = st.toggle(
                "🎼 **Attiva Indirizzo Musicale (32h)**",
                value=has_mus_curr,
                key="tab1_toggle_musical_curriculum"
            )
            problem.config.has_musical_curriculum = has_mus
        with col_m_info:
            if has_mus:
                st.success("✅ **Indirizzo Musicale Attivo**: le classi della sezione musicale effettuano 32 ore settimanali.")
            else:
                st.info("ℹ️ Indirizzo Musicale disattivato.")

        if has_mus:
            all_sections = sorted(list(set(c.section for c in problem.classes.values()))) if problem.classes else ["A", "B", "C", "D", "E", "F"]
            cur_mus_sec = getattr(problem.config, "musical_section", "") or ("F" if "F" in all_sections else (all_sections[0] if all_sections else "F"))
            if cur_mus_sec not in all_sections and all_sections:
                cur_mus_sec = all_sections[0]

            c_m_sec, c_m_co = st.columns(2)
            with c_m_sec:
                chosen_mus_sec = st.selectbox(
                    "Sezione a Indirizzo Musicale (32h):",
                    options=all_sections,
                    index=all_sections.index(cur_mus_sec) if cur_mus_sec in all_sections else 0,
                    help="Tutte le classi di questa sezione (es. 1F, 2F, 3F) avranno orario a 32h settimanali."
                )
                problem.config.musical_section = chosen_mus_sec
            with c_m_co:
                co_doc_num = st.slider(
                    "Docenti in compresenza per Orchestra:", 
                    min_value=1, max_value=4, 
                    value=int(getattr(problem.config, "musical_orchestra_co_teachers", 4)), 
                    step=1
                )
                problem.config.musical_orchestra_co_teachers = co_doc_num

            inst_txt = st.text_input(
                "Strumenti musicali attivi (separati da virgola):", 
                value=", ".join(getattr(problem.config, "musical_instruments", ["Flauto", "Violino", "Chitarra", "Clarinetto"]))
            )
            problem.config.musical_instruments = [x.strip() for x in inst_txt.split(",") if x.strip()]

            # Inietta le 2h di orchestra e assicura i docenti A-56
            orch_subj_id = "orch"
            solf_subj_id = "solf"
            if orch_subj_id not in problem.subjects:
                problem.subjects[orch_subj_id] = Subject(id=orch_subj_id, name="Musica d'Insieme (Orchestra)", color="#d97706", cdc="A-56 / A-30", is_musical_discipline=True, default_double_hours=False)
            if solf_subj_id not in problem.subjects:
                problem.subjects[solf_subj_id] = Subject(id=solf_subj_id, name="Teoria e Solfeggio / Lettura", color="#b45309", cdc="A-56 / A-30", is_musical_discipline=True, default_double_hours=False)

            inst_teachers = [
                ("doc_str_violino", "Prof. Brutti Ilario (Violino)", "A-56 Violino"),
                ("doc_str_clarinetto", "Prof. Carriglio Antonino (Clarinetto)", "A-56 Clarinetto"),
                ("doc_str_flauto", "Prof.ssa Pelaez Pamela (Flauto)", "A-56 Flauto"),
                ("doc_str_chitarra", "Prof. Yague Yuri (Chitarra)", "A-56 Chitarra")
            ]
            for tid, tname, tcdc in inst_teachers:
                if tid not in problem.teachers:
                    problem.teachers[tid] = Teacher(
                        id=tid, name=tname, cdc=tcdc, is_part_time=False,
                        contract_hours=18, max_working_days=5,
                        max_daily_hours=5, max_consecutive_hours=4, max_gap_hours=2
                    )

            co_teachers_ids = ["doc_str_clarinetto", "doc_str_flauto", "doc_str_chitarra"]
            for c_id, c_obj in problem.classes.items():
                if c_obj.section == chosen_mus_sec:
                    c_obj.curriculum_type = "musicale"
                    c_obj.weekly_hours_target = 32
                    c_orch_assigns = [a for a in problem.assignments if a.class_id == c_id and a.subject_id == orch_subj_id]
                    if not c_orch_assigns:
                        problem.assignments.append(TeachingAssignment(
                            id=f"a_{c_id}_orch_doc_str_violino".lower(),
                            teacher_id="doc_str_violino",
                            class_id=c_id,
                            subject_id=orch_subj_id,
                            hours_per_week=2,
                            force_double_hours=False,
                            max_daily_hours=1,
                            co_teacher_ids=co_teachers_ids,
                            preferred_time_of_day="any",
                            preferred_room_id="auditorium" if "auditorium" in problem.rooms else None
                        ))

            st.markdown("##### 📅 Pomeriggi di Rientro, Pausa Mensa & Compresenze:")
            mus_classes_list = [c for c in problem.classes.values() if c.section == chosen_mus_sec or c.curriculum_type == "musicale"]
            if mus_classes_list:
                for mus_c in mus_classes_list:
                    c_col_n, c_col_d, c_col_m = st.columns([1.2, 2.0, 1.2])
                    with c_col_n:
                        st.markdown(f"**Classe {mus_c.name}** *(32h)*")
                    with c_col_d:
                        chosen_aft = st.multiselect(f"Pomeriggi rientro {mus_c.name}", options=DAYS_OF_WEEK[:problem.config.num_days], default=getattr(mus_c, "afternoon_days", []) or [DAYS_OF_WEEK[0]], key=f"mus_class_aft_sel_{mus_c.id}", label_visibility="collapsed")
                        mus_c.afternoon_days = chosen_aft
                    with c_col_m:
                        c_l = getattr(mus_c, "lunch_break_duration", 60)
                        chosen_c_lunch = st.selectbox(f"Mensa {mus_c.name}", options=[0, 30, 60, 90], index=[0, 30, 60, 90].index(c_l) if c_l in [0, 30, 60, 90] else 2, format_func=lambda m: "🚫 No Mensa (7ªh lez.)" if m == 0 else f"🍝 {m} min", key=f"mus_class_lunch_sel_{mus_c.id}", label_visibility="collapsed")
                        mus_c.lunch_break_duration = chosen_c_lunch

                st.markdown("##### 📌 Fissaggio Esatto Slot Orari Compresenza (Orchestra):")
                for mus_c in mus_classes_list:
                    c_orch_assign = next((a for a in problem.assignments if a.class_id == mus_c.id and a.subject_id in ["orch", "solf"]), None)
                    if c_orch_assign:
                        cur_pins = getattr(c_orch_assign, "pinned_slots", []) or []
                        c_p_title, c_p_d1, c_p_h1, c_p_d2, c_p_h2 = st.columns([1.5, 1.3, 1.1, 1.3, 1.1])
                        with c_p_title:
                            st.markdown(f"🎻 **{mus_c.name}** (Orchestra):")
                        def_sch = {"d1": 0, "h1": 6, "d2": 2, "h2": 3}
                        with c_p_d1:
                            p1_d = cur_pins[0][0] if len(cur_pins) > 0 and cur_pins[0][0] < problem.config.num_days else def_sch["d1"]
                            sel_d1 = st.selectbox(f"1ªh Giorno {mus_c.name}", DAYS_OF_WEEK[:problem.config.num_days], index=p1_d, key=f"pin_mus_d1_{mus_c.id}", label_visibility="collapsed")
                            idx_d1 = DAYS_OF_WEEK.index(sel_d1)
                        with c_p_h1:
                            sel_h1 = st.selectbox(f"1ªh Ora {mus_c.name}", list(range(9)), index=min(cur_pins[0][1] if len(cur_pins) > 0 else def_sch["h1"], 8), format_func=lambda x: f"{x+1}ª ora", key=f"pin_mus_h1_{mus_c.id}", label_visibility="collapsed")
                        with c_p_d2:
                            p2_d = cur_pins[1][0] if len(cur_pins) > 1 and cur_pins[1][0] < problem.config.num_days else def_sch["d2"]
                            sel_d2 = st.selectbox(f"2ªh Giorno {mus_c.name}", DAYS_OF_WEEK[:problem.config.num_days], index=p2_d, key=f"pin_mus_d2_{mus_c.id}", label_visibility="collapsed")
                            idx_d2 = DAYS_OF_WEEK.index(sel_d2)
                        with c_p_h2:
                            sel_h2 = st.selectbox(f"2ªh Ora {mus_c.name}", list(range(9)), index=min(cur_pins[1][1] if len(cur_pins) > 1 else def_sch["h2"], 8), format_func=lambda x: f"{x+1}ª ora", key=f"pin_mus_h2_{mus_c.id}", label_visibility="collapsed")
                        c_orch_assign.pinned_slots = [[idx_d1, sel_h1], [idx_d2, sel_h2]]

    # -------------------------------------------------------------
    # 5. ACCORDION 4: TEMPO PROLUNGATO (36h)
    # -------------------------------------------------------------
    has_ext_curr = bool(getattr(problem.config, "has_extended_curriculum", False))
    with st.expander(f"🕒 Tempo Prolungato (36 Ore - con 2 Rientri e Mensa) {'🟢 [ATTIVO]' if has_ext_curr else '⚪ [DISATTIVATO]'}", expanded=has_ext_curr):
        col_p_tog, col_p_info = st.columns([1.5, 2.5])
        with col_p_tog:
            has_ext = st.toggle(
                "🕒 **Attiva Tempo Prolungato (36h)**",
                value=has_ext_curr,
                key="tab1_toggle_extended_curriculum"
            )
            problem.config.has_extended_curriculum = has_ext
        with col_p_info:
            if has_ext:
                st.success("✅ **Tempo Prolungato Attivo**: configurazione 36h settimanali con 2 rientri pomeridiani.")
            else:
                st.info("ℹ️ Tempo Prolungato disattivato.")

        if has_ext:
            all_sections_ext = sorted(list(set(c.section for c in problem.classes.values()))) if problem.classes else ["A", "B", "C", "D", "E", "F"]
            cur_ext_sec = getattr(problem.config, "extended_section", "") or ("D" if "D" in all_sections_ext else (all_sections_ext[0] if all_sections_ext else "D"))
            c_ext_s1, c_ext_s2 = st.columns(2)
            with c_ext_s1:
                chosen_ext_sec = st.selectbox("Sezione a Tempo Prolungato (36h):", options=["Tutte Selezionate Manualmente"] + all_sections_ext, index=(all_sections_ext.index(cur_ext_sec) + 1) if cur_ext_sec in all_sections_ext else 0)
                if chosen_ext_sec != "Tutte Selezionate Manualmente":
                    problem.config.extended_section = chosen_ext_sec
                    for c_obj in problem.classes.values():
                        if c_obj.section == chosen_ext_sec and getattr(c_obj, "curriculum_type", "") != "musicale":
                            c_obj.curriculum_type = "prolungato"; c_obj.weekly_hours_target = 36
            with c_ext_s2:
                ext_lunch_opts = [0, 30, 60, 90]
                cur_ext_l = getattr(problem.config, "default_lunch_break_duration", 60)
                sel_ext_lunch = st.selectbox("Pausa Mensa Tempo Prolungato:", options=ext_lunch_opts, index=ext_lunch_opts.index(cur_ext_l) if cur_ext_l in ext_lunch_opts else 2, format_func=lambda m: "🚫 Nessuna Mensa" if m == 0 else f"🍝 {m} minuti", key="ext_lunch_sel_box")
                problem.config.default_lunch_break_duration = sel_ext_lunch

            ext_classes_list = [c for c in problem.classes.values() if getattr(c, "curriculum_type", "ordinario") == "prolungato"]
            if ext_classes_list:
                for ext_c in ext_classes_list:
                    cur_ext_aft = getattr(ext_c, "afternoon_days", []) or ["Martedì", "Giovedì"]
                    chosen_ext_aft = st.multiselect(f"Pomeriggi rientro {ext_c.name} (36h):", options=DAYS_OF_WEEK[:problem.config.num_days], default=[d for d in cur_ext_aft if d in DAYS_OF_WEEK[:problem.config.num_days]], key=f"ext_class_aft_sel_{ext_c.id}")
                    ext_c.afternoon_days = chosen_ext_aft
            else:
                st.info("Nessuna classe attualmente impostata a Tempo Prolungato (36h). Puoi impostarla dalla Scheda 3.")
        else:
            for c_obj in problem.classes.values():
                if getattr(c_obj, "curriculum_type", "ordinario") == "prolungato":
                    c_obj.curriculum_type = "ordinario"
                    c_obj.weekly_hours_target = 30



# =============================================================
# TAB 2: DOCENTI & DESIDERATA PERSONALI
# =============================================================
with tabs[1]:
    st.header("👥 Docenti & Desiderata Personali")
    
    if st.session_state.get("teacher_save_success"):
        st.success(st.session_state.pop("teacher_save_success"))

    is_settimana_corta = (problem.config.num_days == 5)
    if is_settimana_corta:
        st.info("📌 **Regola Settimana Corta (5 Giorni)**: Il sabato è già giorno di chiusura dell'istituto. I docenti a **tempo pieno** lavorano su tutti i 5 giorni feriali. Il **giorno libero infrasettimanale** è selezionabile solo per i docenti in **Part-time / Orario ridotto**.")
    else:
        st.info("📌 **Regola Settimana Lunga (6 Giorni)**: Tutti i docenti possono esprimere 1ª e 2ª scelta per il giorno libero settimanale.")
    
    if "editing_teacher_id" not in st.session_state:
        st.session_state.editing_teacher_id = None
    
    with st.expander("➕ Inserisci Nuovo Docente (Cattedra, Didattica & Desiderata)", expanded=False):
        render_teacher_edit_card(problem, target_t=None, is_inline=False)
    
    # -------------------------------------------------------------
    # ELENCO DOCENTI REGISTRATI CON FILTRI E BADGE
    # -------------------------------------------------------------
    pt_count = sum(1 for t in problem.teachers.values() if getattr(t, "is_part_time", False))
    ft_count = len(problem.teachers) - pt_count
    
    st.subheader(f"📋 Elenco Docenti Registrati ({len(problem.teachers)})")
    
    # Metriche riepilogative docenti
    m_doc1, m_doc2, m_doc3 = st.columns(3)
    with m_doc1:
        st.metric("👥 Totale Docenti", f"{len(problem.teachers)}")
    with m_doc2:
        st.metric("💼 Tempo Pieno (18h)", f"{ft_count}")
    with m_doc3:
        st.metric("⏱️ Part-Time / Spezzoni", f"{pt_count}")
    
    # Filtro rapido e ricerca
    f_c1, f_c2 = st.columns([2, 3])
    with f_c1:
        filter_doc_type = st.radio(
            "Filtra tipologia contratto:",
            [f"Tutti ({len(problem.teachers)})", f"⏱️ Solo Part-Time ({pt_count})", f"💼 Solo Tempo Pieno ({ft_count})"],
            horizontal=True,
            key="tab2_filter_doc_type"
        )
    with f_c2:
        search_doc_name = st.text_input("🔍 Cerca docente per nome o disciplina:", placeholder="es. De Luca, Fontana, Lombardi, Moretti...", key="tab2_search_doc")
    
    if problem.teachers:
        # PANNELLO SELEZIONE MULTIPLA E CANCELLAZIONE IN BLOCCO DOCENTI
        with st.expander("🗑️ Gestione Multipla & Cancellazione in Blocco Docenti", expanded=False):
            st.caption("Seleziona più docenti da eliminare contemporaneamente o svuota l'intero organico con un click.")
            
            # Calcola docenti visibili in base ai filtri
            vis_tids = []
            for tid, t in problem.teachers.items():
                is_pt = getattr(t, "is_part_time", False)
                if "Solo Part-Time" in filter_doc_type and not is_pt: continue
                if "Solo Tempo Pieno" in filter_doc_type and is_pt: continue
                if search_doc_name:
                    s_query = search_doc_name.lower().strip()
                    if not ((s_query in t.name.lower()) or (getattr(t, "cdc", "") and s_query in t.cdc.lower()) or (s_query in tid.lower())):
                        continue
                vis_tids.append(tid)
    
            sel_col_b1, sel_col_b2 = st.columns([1, 1])
            with sel_col_b1:
                if st.button(f"☑️ Seleziona Tutti i Docenti Visibili ({len(vis_tids)})", use_container_width=True, key="btn_sel_all_doc"):
                    st.session_state["tab2_batch_doc_sel"] = list(vis_tids)
                    st.rerun()
            with sel_col_b2:
                if st.button("⬜ Deseleziona Tutti", use_container_width=True, key="btn_desel_all_doc"):
                    st.session_state["tab2_batch_doc_sel"] = []
                    st.rerun()
    
            cur_batch_sel = st.session_state.get("tab2_batch_doc_sel", [])
            # Mantieni solo ID validi
            cur_batch_sel = [t for t in cur_batch_sel if t in problem.teachers]
            
            chosen_batch_docs = st.multiselect(
                "Docenti selezionati per l'eliminazione:",
                options=list(problem.teachers.keys()),
                default=cur_batch_sel,
                format_func=lambda x: f"{problem.teachers[x].name} ({get_teacher_subjects_display(problem.teachers[x], problem)}) - {sum(a.hours_per_week for a in problem.assignments if a.teacher_id == x)}h",
                key="tab2_batch_doc_sel_widget"
            )
            st.session_state["tab2_batch_doc_sel"] = chosen_batch_docs
    
            del_action_col1, del_action_col2 = st.columns([2, 2])
            with del_action_col1:
                if chosen_batch_docs:
                    if st.button(f"🗑️ Elimina i {len(chosen_batch_docs)} Docenti Selezionati", type="primary", use_container_width=True, key="btn_do_batch_del_doc"):
                        for t_del_id in chosen_batch_docs:
                            if t_del_id in problem.teachers:
                                del problem.teachers[t_del_id]
                            problem.assignments = [a for a in problem.assignments if a.teacher_id != t_del_id]
                        st.session_state["tab2_batch_doc_sel"] = []
                        if st.session_state.editing_teacher_id in chosen_batch_docs:
                            st.session_state.editing_teacher_id = None
                        st.success(f"Eliminati con successo {len(chosen_batch_docs)} docenti e le relative cattedre!")
                        st.rerun()
                else:
                    st.button("🗑️ Elimina Docenti Selezionati (0)", disabled=True, use_container_width=True, key="btn_do_batch_del_doc_dis")
    
            with del_action_col2:
                with st.popover("⚠️ Svuota / Elimina TUTTI i Docenti", use_container_width=True):
                    st.error(f"Sei sicuro di voler eliminare TUTTI i {len(problem.teachers)} docenti della scuola e tutte le cattedre associate?")
                    chk_confirm_del_all_t = st.checkbox("Sì, confermo la cancellazione totale dei docenti", key="chk_conf_del_all_teachers")
                    if st.button("🚨 CONFERMA CANCELLAZIONE TOTALE DOCENTI", type="primary", disabled=not chk_confirm_del_all_t, use_container_width=True):
                        problem.teachers.clear()
                        problem.assignments.clear()
                        st.session_state["tab2_batch_doc_sel"] = []
                        st.session_state.editing_teacher_id = None
                        st.success("Tutti i docenti e le cattedre sono stati eliminati!")
                        st.rerun()
    
        st.caption("Usa le azioni multiple sopra per cancellare in blocco, oppure l'icona ✏️ / 🗑️ su ciascuna riga.")
        
        # Header Tabella Docenti (reattivo a 5 vs 6 giorni)
        if is_settimana_corta:
            hdr_cols = st.columns([3, 2, 3, 1, 1])
            with hdr_cols[0]: st.markdown("**Docente & Cattedra**")
            with hdr_cols[1]: st.markdown("**Contratto**")
            with hdr_cols[2]: st.markdown("**Desiderata / Vincoli Orari**")
            with hdr_cols[3]: st.markdown("**Modifica**")
            with hdr_cols[4]: st.markdown("**Elimina**")
        else:
            hdr_cols = st.columns([3, 2, 2, 2, 1, 1])
            with hdr_cols[0]: st.markdown("**Docente & Cattedra**")
            with hdr_cols[1]: st.markdown("**Contratto**")
            with hdr_cols[2]: st.markdown("**Giorno Libero**")
            with hdr_cols[3]: st.markdown("**Desiderata / Vincoli**")
            with hdr_cols[4]: st.markdown("**Modifica**")
            with hdr_cols[5]: st.markdown("**Elimina**")
            
        st.divider()
    
        visible_teachers_count = 0
        for tid, t in problem.teachers.items():
            is_pt = getattr(t, "is_part_time", False)
            
            # Filtro tipo contratto
            if "Solo Part-Time" in filter_doc_type and not is_pt:
                continue
            if "Solo Tempo Pieno" in filter_doc_type and is_pt:
                continue
                
            # Filtro ricerca testuale
            if search_doc_name:
                s_query = search_doc_name.lower().strip()
                t_matches = (s_query in t.name.lower()) or (getattr(t, "cdc", "") and s_query in t.cdc.lower()) or (s_query in tid.lower())
                if not t_matches:
                    continue
    
            visible_teachers_count += 1
            unavail_count = len(getattr(t, "unavailable_slots", []))
            soft_count = len(getattr(t, "soft_avoid_slots", []))
            contract_h = getattr(t, "contract_hours", None)
            max_w_days = getattr(t, "max_working_days", None)
            
            if is_pt:
                pt_details = []
                if contract_h:
                    pt_details.append(f"{contract_h}h")
                if max_w_days:
                    pt_details.append(f"max {max_w_days} gg")
                contratto_label = f"⏱️ **Part-Time** ({', '.join(pt_details)})"
            else:
                contratto_label = "💼 Tempo Pieno (18h)"

            f_list = []
            if getattr(t, "free_day_1", None): f_list.append(t.free_day_1)
            if getattr(t, "free_day_2", None): f_list.append(t.free_day_2)
            giorno_libero_str = ", ".join(f_list) if f_list else "-"
    
            req_count = len(getattr(t, "required_slots", []))
            t_assigns = [a for a in problem.assignments if a.teacher_id == tid or tid in getattr(a, "co_teacher_ids", [])]
            pinned_count = sum(len(getattr(a, "pinned_slots", [])) for a in t_assigns)
    
            desiderata_tags = []
            has_triple_ita = (getattr(problem.config, "force_triple_hours_italian", False) and any(a.subject_id == "ita" for a in t_assigns)) or any(getattr(a, "force_triple_hours", False) for a in t_assigns)
            if has_triple_ita:
                desiderata_tags.append("📝 3h Tema 🔒")
            if req_count > 0:
                desiderata_tags.append(f"🟢 {req_count}h fisse 🔒")
            if pinned_count > 0:
                desiderata_tags.append(f"📌 {pinned_count} lez. bloccate 🔒")
            if unavail_count > 0:
                desiderata_tags.append(f"🔴 {unavail_count}h no")
            if getattr(t, "prefer_late_entry", False):
                desiderata_tags.append("🌅 Tardi")
            if getattr(t, "prefer_early_exit", False):
                desiderata_tags.append("🌇 Presto")
            if soft_count > 0:
                desiderata_tags.append(f"🟡 {soft_count} slot")
            desiderata_str = ", ".join(desiderata_tags) if desiderata_tags else "Standard"
    
            is_sos = (
                "sostegno" in t.name.lower() 
                or "sostegno" in getattr(t, "cdc", "").lower() 
                or "admm" in getattr(t, "cdc", "").lower()
                or bool(getattr(t, "preferred_areas", []))
            )
            if is_sos:
                p_areas = getattr(t, "preferred_areas", [])
                if p_areas:
                    area_badges = [DISCIPLINARY_AREAS[k]["label"] for k in p_areas if k in DISCIPLINARY_AREAS]
                    classes_txt = f"🎯 *Aree preferite: {', '.join(area_badges)}*"
                else:
                    classes_txt = "🎯 *Aree preferite: Tutte le discipline (generale)*"
            else:
                assigned_classes_names = sorted(list(set(problem.classes[a.class_id].name if a.class_id in problem.classes else a.class_id for a in t_assigns)))
                tot_h_assigned = sum(a.hours_per_week for a in t_assigns)
                has_co = any(tid in getattr(a, "co_teacher_ids", []) for a in t_assigns)
                co_tag = " *(in compresenza)*" if (has_co and not any(a.teacher_id == tid for a in t_assigns)) else ""
                classes_txt = f"📚 *Classi: {', '.join(assigned_classes_names)} ({tot_h_assigned}h{co_tag})*" if assigned_classes_names else "📚 *Nessuna classe assegnata*"

            t_subjs_str = get_teacher_subjects_display(t, problem)
            pt_badge = " ⏱️ `[PART-TIME]`" if is_pt else ""
            is_curr_editing = (st.session_state.editing_teacher_id == tid)
    
            if is_settimana_corta:
                row_cols = st.columns([3, 2, 3, 1, 1])
                with row_cols[0]:
                    doc_name_styled = f"👉 **{t.name}**{pt_badge} *(in modifica qui sotto 👇)*  \n📖 *{t_subjs_str}*  \n{classes_txt}" if is_curr_editing else f"**{t.name}**{pt_badge}  \n📖 *{t_subjs_str}*  \n{classes_txt}"
                    st.markdown(doc_name_styled)
                with row_cols[1]:
                    st.markdown(contratto_label)
                with row_cols[2]:
                    st.caption(desiderata_str)
                with row_cols[3]:
                    edit_icon = "❌" if is_curr_editing else "✏️"
                    edit_help = f"Chiudi modifica di {t.name}" if is_curr_editing else f"Modifica {t.name} direttamente qui sotto"
                    if st.button(edit_icon, key=f"edit_btn_{tid}", help=edit_help):
                        if is_curr_editing:
                            st.session_state.editing_teacher_id = None
                        else:
                            st.session_state.editing_teacher_id = tid
                        st.rerun()
                with row_cols[4]:
                    if st.button("🗑️", key=f"del_btn_{tid}", help=f"Elimina {t.name}"):
                        del problem.teachers[tid]
                        problem.assignments = [a for a in problem.assignments if a.teacher_id != tid]
                        if st.session_state.editing_teacher_id == tid:
                            st.session_state.editing_teacher_id = None
                        st.success(f"Docente eliminato!")
                        st.rerun()
            else:
                row_cols = st.columns([3, 2, 2, 2, 1, 1])
                with row_cols[0]:
                    doc_name_styled = f"👉 **{t.name}**{pt_badge} *(in modifica qui sotto 👇)*  \n📖 *{t_subjs_str}*  \n{classes_txt}" if is_curr_editing else f"**{t.name}**{pt_badge}  \n📖 *{t_subjs_str}*  \n{classes_txt}"
                    st.markdown(doc_name_styled)
                with row_cols[1]:
                    st.markdown(contratto_label)
                with row_cols[2]:
                    st.write(giorno_libero_str)
                with row_cols[3]:
                    st.caption(desiderata_str)
                with row_cols[4]:
                    edit_icon = "❌" if is_curr_editing else "✏️"
                    edit_help = f"Chiudi modifica di {t.name}" if is_curr_editing else f"Modifica {t.name} direttamente qui sotto"
                    if st.button(edit_icon, key=f"edit_btn_{tid}", help=edit_help):
                        if is_curr_editing:
                            st.session_state.editing_teacher_id = None
                        else:
                            st.session_state.editing_teacher_id = tid
                        st.rerun()
                with row_cols[5]:
                    if st.button("🗑️", key=f"del_btn_{tid}", help=f"Elimina {t.name}"):
                        del problem.teachers[tid]
                        problem.assignments = [a for a in problem.assignments if a.teacher_id != tid]
                        if st.session_state.editing_teacher_id == tid:
                            st.session_state.editing_teacher_id = None
                        st.success(f"Docente eliminato!")
                        st.rerun()
    
            # MODIFICA INLINE SUBITO SOTTO IL DOCENTE IN ELENCO
            if is_curr_editing:
                st.markdown(f"""
                <div class="edit-banner-teacher">
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                        <span style="font-size: 1.25rem; font-weight: 800; color: #1e40af;">✏️ SCHEDA DI MODIFICA: <u>{t.name}</u></span>
                        <span style="background: #2563eb; color: white; padding: 4px 12px; border-radius: 14px; font-size: 0.85rem; font-weight: 700;">📖 {t_subjs_str}</span>
                    </div>
                    <div style="font-size: 0.93rem; color: #1e3a8a; margin-top: 6px; font-weight: 500;">
                        ⬇️ Tutti i dati, la cattedra, le classi e i desiderata di <b>{t.name}</b> sono modificabili nel riquadro azzurro sottostante. Salva con <b>💾 Salva Modifiche Docente</b> in fondo.
                    </div>
                </div>
                """, unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown('<div class="edit-box-teacher-indicator"></div>', unsafe_allow_html=True)
                    render_teacher_edit_card(problem, target_t=t, is_inline=True)
    
        if visible_teachers_count == 0:
            if not problem.teachers:
                st.warning("⚠️ Nessun docente registrato nella sessione corrente.")
                if st.button("🔄 Ripristina e Carica Subito l'Organico Docenti Demo (30 Docenti)", type="primary", key="btn_restore_teachers_tab2"):
                    demo_p = get_sample_problem(num_classes=len(problem.classes) or 18, is_dada=getattr(problem.config, "is_dada", False))
                    problem.teachers = demo_p.teachers
                    problem.assignments = demo_p.assignments
                    st.rerun()
            else:
                st.info("Nessun docente corrisponde ai criteri di filtro o ricerca selezionati.")
                if st.button("🔄 Mostra Tutti i Docenti (Azzera Filtri)", key="btn_reset_filters_t"):
                    st.session_state["tab2_search_doc"] = ""
                    st.rerun()
    else:
        st.warning("⚠️ Nessun docente registrato nella sessione corrente.")
        if st.button("🔄 Ripristina e Carica Subito l'Organico Docenti Demo (30 Docenti)", type="primary", key="btn_restore_teachers_tab2_empty"):
            demo_p = get_sample_problem(num_classes=len(problem.classes) or 18, is_dada=getattr(problem.config, "is_dada", False))
            problem.teachers = demo_p.teachers
            problem.assignments = demo_p.assignments
            st.rerun()
    
# =============================================================
# TAB 3: CLASSI, MATERIE, AULE & CONSIGLI DI CLASSE
# =============================================================
with tabs[2]:
    st.header("👥 Docenti, Cattedre & Consigli di Classe")
    st.caption("Configura le classi, le materie, le aule/laboratori con docenti assegnati e il quadro didattico del consiglio di classe.")
    
    subtab_classi, subtab_materie, subtab_aule, subtab_consigli = st.tabs([
        "🎓 1. Classi della Scuola",
        "📖 2. Materie di Insegnamento",
        "🏢 3. Aule, Laboratori & Docenti Assegnati",
        "📋 4. Consiglio di Classe (Assegnazione per Classe)"
    ])

    # -------------------------------------------------------------
    # SOTTOSCHEDA 1: CLASSI DELLA SCUOLA
    # -------------------------------------------------------------
    with subtab_classi:
        st.subheader("🎓 Classi della Scuola Media")
        with st.expander("➕ Nuova Classe", expanded=False):
            c_name = st.text_input("Nome Classe", placeholder="es. 1ª A, 1ª F Musicale, 2ª E Prolungato")
            c_c1, c_c2 = st.columns(2)
            with c_c1:
                c_grade = st.selectbox("Anno di Corso", [1, 2, 3], format_func=lambda x: f"{x}ª Media")
                c_sec = st.text_input("Sezione", value="A")
            with c_c2:
                c_curr = st.selectbox("Indirizzo / Tempo Scuola", ["ordinario", "musicale", "prolungato"], format_func=lambda x: "🟢 Tempo Ordinario (30h)" if x=="ordinario" else ("🎼 Indirizzo Musicale (32h)" if x=="musicale" else "🕒 Tempo Prolungato (36h)"))
                target_h_calc = 30 if c_curr=="ordinario" else (32 if c_curr=="musicale" else 36)
            
            c_afternoons = []
            if c_curr in ["musicale", "prolungato"]:
                c_afternoons = st.multiselect("Giorni di Rientro Pomeridiano per questa classe:", DAYS_OF_WEEK[:problem.config.num_days], default=["Lunedì"] if c_curr=="musicale" else ["Martedì", "Giovedì"])
            
            if st.button("Aggiungi Classe", type="primary"):
                if c_name:
                    c_id = c_name.replace(" ", "_").replace("ª", "").lower()
                    problem.classes[c_id] = SchoolClass(
                        id=c_id, 
                        name=c_name, 
                        grade=c_grade, 
                        section=c_sec,
                        curriculum_type=c_curr,
                        weekly_hours_target=target_h_calc,
                        afternoon_days=c_afternoons
                    )
                    st.success(f"Classe {c_name} inserita!")
                    st.rerun()
                else:
                    st.warning("Inserisci il nome della classe.")
                    
        if problem.classes:
            classes_rows = []
            for c in problem.classes.values():
                curr_badge = "🟢 Ordinario (30h)" if getattr(c, "curriculum_type", "ordinario") == "ordinario" else ("🎼 Musicale (32h)" if c.curriculum_type == "musicale" else "🕒 Prolungato (36h)")
                rientri_txt = ", ".join(getattr(c, "afternoon_days", [])) if getattr(c, "afternoon_days", []) else "-"
                classes_rows.append({
                    "ID": c.id, 
                    "Nome Classe": c.name, 
                    "Anno": f"{c.grade}ª Media", 
                    "Sezione": c.section,
                    "Indirizzo": curr_badge,
                    "Rientri Pomeridiani": rientri_txt
                })
            classes_df = pd.DataFrame(classes_rows)
            st.dataframe(classes_df, use_container_width=True, hide_index=True)
            
            with st.expander("🗑️ Gestione Multipla & Cancellazione in Blocco Classi", expanded=False):
                st.caption("Seleziona più classi da eliminare o cancella l'intero plesso scolastico.")
                sel_c_all_col1, sel_c_all_col2 = st.columns(2)
                with sel_c_all_col1:
                    if st.button(f"☑️ Seleziona Tutte le Classi ({len(problem.classes)})", use_container_width=True, key="btn_sel_all_classes"):
                        st.session_state["tab3_batch_class_sel"] = list(problem.classes.keys())
                        st.rerun()
                with sel_c_all_col2:
                    if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_desel_all_classes"):
                        st.session_state["tab3_batch_class_sel"] = []
                        st.rerun()

                cur_c_sel = [c for c in st.session_state.get("tab3_batch_class_sel", []) if c in problem.classes]
                chosen_batch_classes = st.multiselect(
                    "Classi selezionate per l'eliminazione:",
                    options=list(problem.classes.keys()),
                    default=cur_c_sel,
                    format_func=lambda x: f"Classe {problem.classes[x].name}",
                    key="tab3_batch_class_sel_widget"
                )
                st.session_state["tab3_batch_class_sel"] = chosen_batch_classes

                act_c1, act_c2 = st.columns(2)
                with act_c1:
                    if chosen_batch_classes:
                        if st.button(f"🗑️ Elimina le {len(chosen_batch_classes)} Classi Selezionate", type="primary", use_container_width=True, key="btn_del_batch_classes"):
                            for c_del_id in chosen_batch_classes:
                                if c_del_id in problem.classes:
                                    del problem.classes[c_del_id]
                                problem.assignments = [a for a in problem.assignments if a.class_id != c_del_id]
                            st.session_state["tab3_batch_class_sel"] = []
                            st.success(f"Eliminate {len(chosen_batch_classes)} classi e le relative cattedre!")
                            st.rerun()
                    else:
                        st.button("🗑️ Elimina Classi Selezionate (0)", disabled=True, use_container_width=True, key="btn_del_batch_classes_dis")

                with act_c2:
                    with st.popover("⚠️ Svuota / Elimina TUTTE le Classi", use_container_width=True):
                        st.error(f"Vuoi eliminare TUTTE le {len(problem.classes)} classi e le relative cattedre?")
                        chk_conf_del_all_c = st.checkbox("Sì, confermo la cancellazione totale delle classi", key="chk_conf_del_all_classes")
                        if st.button("🚨 CONFERMA ELIMINAZIONE TUTTE LE CLASSI", type="primary", disabled=not chk_conf_del_all_c, use_container_width=True):
                            problem.classes.clear()
                            problem.assignments.clear()
                            st.session_state["tab3_batch_class_sel"] = []
                            st.success("Tutte le classi e le cattedre sono state eliminate!")
                            st.rerun()

    # -------------------------------------------------------------
    # SOTTOSCHEDA 2: MATERIE DI INSEGNAMENTO
    # -------------------------------------------------------------
    with subtab_materie:
        st.subheader("📖 Materie di Insegnamento")
        with st.expander("➕ Nuova Materia", expanded=False):
            m_id = st.text_input("ID Materia", placeholder="es. mat, ita, sci")
            m_name = st.text_input("Nome Materia", placeholder="es. Matematica, Italiano")
            m_color = st.color_picker("Colore Identificativo", "#2980b9")
            
            room_options = ["Nessuna"] + list(problem.rooms.keys())
            m_room = st.selectbox("Laboratorio Specifico (opzionale)", room_options, format_func=lambda x: problem.rooms[x].name if x in problem.rooms else x)
            
            if st.button("Aggiungi Materia"):
                if m_id and m_name:
                    problem.subjects[m_id] = Subject(
                        id=m_id, 
                        name=m_name, 
                        color=m_color, 
                        special_room_id=m_room if m_room != "Nessuna" else None
                    )
                    st.success(f"Materia {m_name} aggiunta!")
                    st.rerun()
                else:
                    st.warning("Inserisci ID e Nome materia.")
                    
        if problem.subjects:
            subj_list = []
            for s in problem.subjects.values():
                room_txt = problem.rooms[s.special_room_id].name if s.special_room_id in problem.rooms else "-"
                subj_list.append({"ID": s.id, "Materia": s.name, "Colore": s.color, "Aula/Lab": room_txt})
            st.dataframe(pd.DataFrame(subj_list), use_container_width=True, hide_index=True)
            
            with st.expander("🗑️ Gestione Multipla & Cancellazione in Blocco Materie", expanded=False):
                st.caption("Seleziona più materie da eliminare o cancella l'intero piano di studi.")
                sel_s_all_col1, sel_s_all_col2 = st.columns(2)
                with sel_s_all_col1:
                    if st.button(f"☑️ Seleziona Tutte le Materie ({len(problem.subjects)})", use_container_width=True, key="btn_sel_all_subjs"):
                        st.session_state["tab3_batch_subj_sel"] = list(problem.subjects.keys())
                        st.rerun()
                with sel_s_all_col2:
                    if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_desel_all_subjs"):
                        st.session_state["tab3_batch_subj_sel"] = []
                        st.rerun()

                cur_s_sel = [s for s in st.session_state.get("tab3_batch_subj_sel", []) if s in problem.subjects]
                chosen_batch_subjs = st.multiselect(
                    "Materie selezionate per l'eliminazione:",
                    options=list(problem.subjects.keys()),
                    default=cur_s_sel,
                    format_func=lambda x: problem.subjects[x].name,
                    key="tab3_batch_subj_sel_widget"
                )
                st.session_state["tab3_batch_subj_sel"] = chosen_batch_subjs

                act_s1, act_s2 = st.columns(2)
                with act_s1:
                    if chosen_batch_subjs:
                        if st.button(f"🗑️ Elimina le {len(chosen_batch_subjs)} Materie Selezionate", type="primary", use_container_width=True, key="btn_del_batch_subjs"):
                            for s_del_id in chosen_batch_subjs:
                                if s_del_id in problem.subjects:
                                    del problem.subjects[s_del_id]
                                problem.assignments = [a for a in problem.assignments if a.subject_id != s_del_id]
                            st.session_state["tab3_batch_subj_sel"] = []
                            st.success(f"Eliminate {len(chosen_batch_subjs)} materie e le relative cattedre!")
                            st.rerun()
                    else:
                        st.button("🗑️ Elimina Materie Selezionate (0)", disabled=True, use_container_width=True, key="btn_del_batch_subjs_dis")

                with act_s2:
                    with st.popover("⚠️ Svuota / Elimina TUTTE le Materie", use_container_width=True):
                        st.error(f"Vuoi eliminare TUTTE le {len(problem.subjects)} materie e le relative cattedre?")
                        chk_conf_del_all_s = st.checkbox("Sì, confermo la cancellazione totale delle materie", key="chk_conf_del_all_subjs")
                        if st.button("🚨 CONFERMA ELIMINAZIONE TUTTE LE MATERIE", type="primary", disabled=not chk_conf_del_all_s, use_container_width=True):
                            problem.subjects.clear()
                            problem.assignments.clear()
                            st.session_state["tab3_batch_subj_sel"] = []
                            st.success("Tutte le materie e le cattedre sono state eliminate!")
                            st.rerun()

    # -------------------------------------------------------------
    # SOTTOSCHEDA 3: AULE, LABORATORI & PALESTRE
    # -------------------------------------------------------------
    with subtab_aule:
        is_dada_on = getattr(problem.config, "is_dada", False)
        title_spaces = "🏢 Aule DADA, Laboratori & Spazi" if is_dada_on else "🏢 Laboratori & Palestre"
        btn_add_spaces = "➕ Nuova Aula DADA / Laboratorio / Spazio" if is_dada_on else "➕ Aggiungi Laboratorio / Palestra"
        
        st.subheader(title_spaces)
        st.caption("Configura gli spazi della scuola (laboratori speciali, palestre, aule disciplinari DADA) e la loro capienza massima.")
        
        render_room_bottlenecks_resolver(problem, key_suffix="tab3_aule")
    
        if "editing_room_id" not in st.session_state:
            st.session_state.editing_room_id = None
    
        with st.expander(btn_add_spaces, expanded=False):
            render_room_edit_card(problem, target_r=None, is_inline=False)
    
        # Tabella & Riepilogo Aule Esistenti
        if problem.rooms:
            st.markdown(f"##### 🏢 Aule & Laboratori Configurate ({len(problem.rooms)})")
            
            with st.expander("🗑️ Gestione Multipla & Cancellazione in Blocco Aule / Laboratori", expanded=False):
                st.caption("Seleziona più aule da eliminare contemporaneamente o svuota tutti gli spazi con un click.")
                sel_r_all_col1, sel_r_all_col2 = st.columns(2)
                with sel_r_all_col1:
                    if st.button(f"☑️ Seleziona Tutte le Aule ({len(problem.rooms)})", use_container_width=True, key="btn_sel_all_rooms"):
                        st.session_state["tab3_batch_room_sel"] = list(problem.rooms.keys())
                        st.rerun()
                with sel_r_all_col2:
                    if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_desel_all_rooms"):
                        st.session_state["tab3_batch_room_sel"] = []
                        st.rerun()
    
                cur_r_sel = [r for r in st.session_state.get("tab3_batch_room_sel", []) if r in problem.rooms]
                chosen_batch_rooms = st.multiselect(
                    "Aule selezionate per l'eliminazione:",
                    options=list(problem.rooms.keys()),
                    default=cur_r_sel,
                    format_func=lambda x: f"{problem.rooms[x].name} ({'🧪 Lab/Palestra' if problem.rooms[x].is_special_lab else '🏫 Aula/DADA'})",
                    key="tab3_batch_room_sel_widget"
                )
                st.session_state["tab3_batch_room_sel"] = chosen_batch_rooms
    
                act_r1, act_r2 = st.columns(2)
                with act_r1:
                    if chosen_batch_rooms:
                        if st.button(f"🗑️ Elimina le {len(chosen_batch_rooms)} Aule Selezionate", type="primary", use_container_width=True, key="btn_del_batch_rooms"):
                            for r_del_id in chosen_batch_rooms:
                                if r_del_id in problem.rooms:
                                    del problem.rooms[r_del_id]
                            st.session_state["tab3_batch_room_sel"] = []
                            if st.session_state.editing_room_id in chosen_batch_rooms:
                                st.session_state.editing_room_id = None
                            st.success(f"Eliminate {len(chosen_batch_rooms)} aule con successo!")
                            st.rerun()
                    else:
                        st.button("🗑️ Elimina Aule Selezionate (0)", disabled=True, use_container_width=True, key="btn_del_batch_rooms_dis")
    
                with act_r2:
                    with st.popover("⚠️ Svuota / Elimina TUTTE le Aule", use_container_width=True):
                        st.error(f"Vuoi eliminare TUTTE le {len(problem.rooms)} aule e laboratori configurati?")
                        chk_conf_del_all_r = st.checkbox("Sì, confermo la cancellazione totale delle aule", key="chk_conf_del_all_rooms")
                        if st.button("🚨 CONFERMA ELIMINAZIONE TUTTE LE AULE", type="primary", disabled=not chk_conf_del_all_r, use_container_width=True):
                            problem.rooms.clear()
                            st.session_state["tab3_batch_room_sel"] = []
                            st.session_state.editing_room_id = None
                            st.success("Tutte le aule e laboratori sono stati eliminati!")
                            st.rerun()
    
            st.caption("Usa le azioni multiple sopra per cancellare in blocco, oppure l'icona ✏️ / 🗑️ su ciascuna riga.")
            hdr_r = st.columns([3, 2, 1, 1, 2, 2, 1, 1])
            with hdr_r[0]: st.markdown("**Nome Spazio / Aula**")
            with hdr_r[1]: st.markdown("**Tipologia**")
            with hdr_r[2]: st.markdown("**Capienza**")
            with hdr_r[3]: st.markdown("**Priorità**")
            with hdr_r[4]: st.markdown("**Materie Associate**")
            with hdr_r[5]: st.markdown("**Docenti Assegnati**")
            with hdr_r[6]: st.markdown("**Mod.**")
            with hdr_r[7]: st.markdown("**Elim.**")
            st.divider()
    
            for rid, r in problem.rooms.items():
                is_cur_edit_room = (st.session_state.editing_room_id == rid)
                r_type_badge = "🧪 Lab / Speciale" if r.is_special_lab else "🏫 Ordinaria / DADA"
                r_prio = getattr(r, "priority", 1)
                prio_badge = "🥇 Principale" if r_prio == 1 else ("🥈 Secondaria" if r_prio == 2 else "🥉 Riserva")
                
                subjs_names = [problem.subjects[s].name for s in r.subject_ids if s in problem.subjects]
                subjs_txt = ", ".join(subjs_names) if subjs_names else "Tutte / Generica"
                
                teachers_names = [problem.teachers[t].name for t in getattr(r, "teacher_ids", []) if t in problem.teachers]
                teachers_txt = ", ".join(teachers_names) if teachers_names else "Tutti i docenti autorizzati"
    
                row_r = st.columns([3, 2, 1, 1, 2, 2, 1, 1])
                with row_r[0]:
                    if is_cur_edit_room:
                        st.markdown(f"👉 **{r.name}** *(in modifica qui sotto 👇)*  \n`ID: {r.id}`")
                    else:
                        st.markdown(f"**{r.name}**  \n`ID: {r.id}`")
                with row_r[1]:
                    st.caption(r_type_badge)
                with row_r[2]:
                    st.write(f"{r.capacity} cl.")
                with row_r[3]:
                    st.caption(prio_badge)
                with row_r[4]:
                    st.caption(subjs_txt)
                with row_r[5]:
                    if teachers_names:
                        st.markdown(f"👤 **{teachers_txt}** (100% 🔒)")
                    else:
                        st.caption(teachers_txt)
                with row_r[6]:
                    edit_icon = "❌" if is_cur_edit_room else "✏️"
                    edit_help = f"Chiudi modifica di {r.name}" if is_cur_edit_room else f"Modifica aula {r.name} direttamente qui sotto"
                    if st.button(edit_icon, key=f"edit_room_btn_{rid}", help=edit_help):
                        if is_cur_edit_room:
                            st.session_state.editing_room_id = None
                        else:
                            st.session_state.editing_room_id = rid
                        st.rerun()
                with row_r[7]:
                    if st.button("🗑️", key=f"del_room_btn_{rid}", help=f"Elimina aula {r.name}"):
                        del problem.rooms[rid]
                        if st.session_state.editing_room_id == rid:
                            st.session_state.editing_room_id = None
                        st.success(f"Aula eliminata!")
                        st.rerun()
    
                # MODIFICA INLINE SUBITO SOTTO L'AULA IN ELENCO
                if is_cur_edit_room:
                    st.markdown(f"""
                    <div class="edit-banner-room">
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                            <span style="font-size: 1.25rem; font-weight: 800; color: #166534;">✏️ SCHEDA DI MODIFICA SPAZIO / AULA: <u>{r.name}</u></span>
                            <span style="background: #16a34a; color: white; padding: 4px 12px; border-radius: 14px; font-size: 0.85rem; font-weight: 700;">{'LAB / PALESTRA' if r.is_special_lab else 'AULA ORDINARIA / DADA'}</span>
                        </div>
                        <div style="font-size: 0.93rem; color: #14532d; margin-top: 6px; font-weight: 500;">
                            ⬇️ Modifica caratteristiche, capienza, priorità e docenti assegnati a <b>{r.name}</b> qui sotto. Salva con <b>💾 Salva Modifiche Aula</b> in fondo.
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    with st.container(border=True):
                        st.markdown('<div class="edit-box-room-indicator"></div>', unsafe_allow_html=True)
                        render_room_edit_card(problem, target_r=r, is_inline=True)
        else:
            st.warning("⚠️ Nessuna aula o laboratorio presente nella sessione corrente.")
            if st.button("🔄 Carica e Popola Subito Tutte le Aule Demo", type="primary", key="btn_load_demo_rooms"):
                demo_p = get_sample_problem(num_classes=len(problem.classes) or 18, is_dada=getattr(problem.config, "is_dada", False))
                problem.rooms = demo_p.rooms
                st.success(f"Caricate {len(problem.rooms)} aule con successo!")
                st.rerun()
    
    # -------------------------------------------------------------
    # SOTTOSCHEDA 4: CONSIGLIO DI CLASSE (ASSEGNAZIONE PER CLASSE)
    # -------------------------------------------------------------
    with subtab_consigli:
        st.subheader("📋 Assegnazione Docenti & Discipline per Classe (Consiglio di Classe)")
        st.caption("Visualizza l'organico completo dei consigli di classe dell'istituto e modifica l'assegnazione dei docenti per ciascuna classe.")
    
        if problem.classes:
            # 1. QUADRO SINOTTICO GENERALE DEI CONSIGLI DI CLASSE
            st.markdown(f"#### 📊 Quadro Sinottico Generale: Consigli di Classe ({len(problem.classes)} Classi)")
            st.caption("Riepilogo generale delle cattedre e dei docenti titolari assegnati per ciascuna materia e classe.")
            
            subject_order = ["ita", "sto", "geo", "mat", "sci", "ing", "spa", "tec", "mus", "art", "mot", "rel", "tea"]
            all_s_keys = list(problem.subjects.keys())
            ordered_keys = [k for k in subject_order if k in all_s_keys] + [k for k in all_s_keys if k not in subject_order]
    
            sinottico_rows = []
            for c_id, c_obj in problem.classes.items():
                c_assigns = {a.subject_id: a for a in problem.assignments if a.class_id == c_id}
                row_data = {"Classe": f"Classe {c_obj.name}"}
                tot_h = 0
                for s_id in ordered_keys:
                    s_name = problem.subjects[s_id].name
                    if s_id in c_assigns:
                        a_obj = c_assigns[s_id]
                        t_name = problem.teachers[a_obj.teacher_id].name if a_obj.teacher_id in problem.teachers else a_obj.teacher_id
                        row_data[s_name] = f"{t_name} ({a_obj.hours_per_week}h)"
                        tot_h += a_obj.hours_per_week
                    else:
                        row_data[s_name] = "-"
                row_data["Totale Ore"] = f"{tot_h}h / 30h" if tot_h == 30 else f"⚠️ {tot_h}h / 30h"
                sinottico_rows.append(row_data)
    
            if sinottico_rows:
                df_sinottico = pd.DataFrame(sinottico_rows)
                st.dataframe(df_sinottico, use_container_width=True, hide_index=True)
            else:
                st.warning("⚠️ Nessun consiglio di classe o cattedra presente nella sessione corrente.")
                if st.button("🔄 Carica e Popola Subito Tutti i Consigli di Classe Demo", type="primary", key="btn_load_demo_cdc"):
                    demo_p = get_sample_problem(num_classes=len(problem.classes) or 18, is_dada=getattr(problem.config, "is_dada", False))
                    problem.assignments = demo_p.assignments
                    st.success(f"Caricate {len(problem.assignments)} cattedre con successo!")
                    st.rerun()
    
            st.divider()
    
            # 2. EDITOR INTERATTIVO PER SINGOLA CLASSE
            st.markdown("#### ✏️ Modifica e Assegnazione Docenti per Singola Classe")
            sel_class_cfg = st.selectbox(
                "👉 Seleziona la Classe da configurare / modificare:",
                options=list(problem.classes.keys()),
                format_func=lambda x: f"Classe {problem.classes[x].name}",
                key="sel_class_cfg_box"
            )
            
            if sel_class_cfg:
                c_obj = problem.classes[sel_class_cfg]
                st.markdown(f"##### 🏫 Cattedre & Materie: **{c_obj.name}**")
                
                # Recupera le assegnazioni attuali di questa classe
                curr_class_assigns = {a.subject_id: a for a in problem.assignments if a.class_id == sel_class_cfg}
                
                # Lista delle materie tipiche
                subject_order = ["ita", "sto", "geo", "mat", "sci", "ing", "spa", "tec", "mus", "art", "mot", "rel"]
                all_s_keys = list(problem.subjects.keys())
                ordered_keys = [k for k in subject_order if k in all_s_keys] + [k for k in all_s_keys if k not in subject_order]
                
                teacher_opts = ["-- Non assegnato --"] + list(problem.teachers.keys())
                
                new_class_data = []
                cols_h = st.columns([3, 3, 2, 2])
                with cols_h[0]: st.markdown("**Materia**")
                with cols_h[1]: st.markdown("**Docente Incaricato**")
                with cols_h[2]: st.markdown("**Ore Settimana**")
                with cols_h[3]: st.markdown("**Ore Doppie**")
                
                app_sub = getattr(problem.config, "approfondimento_subject", "ita")
    
                has_teatro_in_class = any(s_k == "app_custom" or "teatro" in s_k.lower() for s_k in ordered_keys)
                ita_teacher_found = curr_class_assigns["ita"].teacher_id if "ita" in curr_class_assigns and curr_class_assigns["ita"].teacher_id in problem.teachers else None
    
                for s_id in ordered_keys:
                    s_obj = problem.subjects[s_id]
                    curr_a = curr_class_assigns.get(s_id, None)
                    
                    # Default hours per subject
                    if curr_a:
                        init_h = curr_a.hours_per_week
                        init_teacher = curr_a.teacher_id if curr_a.teacher_id in problem.teachers else "-- Non assegnato --"
                        init_double = curr_a.force_double_hours
                        # Se c'è teatro e italiano era rimasto a 6h, portalo a 5h per evitare 31h
                        if s_id == "ita" and has_teatro_in_class and init_h == 6:
                            init_h = 5
                    else:
                        init_teacher = "-- Non assegnato --"
                        app_type = getattr(problem.config, "approfondimento_type", "subject")
                        ded_from = getattr(problem.config, "approfondimento_deduct_from", "ita")
                        
                        if s_id == "ita":
                            if has_teatro_in_class: init_h = 5
                            elif app_type == "subject" and app_sub == "ita": init_h = 6
                            elif app_type == "custom_activity" and ded_from == "ita": init_h = 5
                            else: init_h = 6
                        elif s_id == "sto":
                            if app_type == "custom_activity" and ded_from == "sto": init_h = 1
                            else: init_h = 2
                        elif s_id == "geo":
                            if app_type == "custom_activity" and ded_from == "geo": init_h = 1
                            else: init_h = 2
                        elif s_id == "mat":
                            if app_type == "subject" and app_sub == "mat": init_h = 5
                            elif app_type == "custom_activity" and ded_from == "mat": init_h = 3
                            else: init_h = 4
                        elif s_id == "sci":
                            if app_type == "subject" and app_sub == "sci": init_h = 3
                            elif app_type == "custom_activity" and ded_from == "sci": init_h = 1
                            else: init_h = 2
                        elif s_id == "ing":
                            init_h = 4 if (app_type == "subject" and app_sub == "ing") else 3
                        elif s_id == "tec":
                            init_h = 3 if (app_type == "subject" and app_sub == "tec") else 2
                        elif s_id == "spa":
                            init_h = 3 if (app_type == "subject" and app_sub == "spa") else 2
                        elif s_id in ["mus", "art", "mot"]:
                            init_h = 2
                        elif s_id == "rel":
                            init_h = 1
                        elif "app_" in s_id or s_id == "app_custom":
                            init_h = 1
                            if ita_teacher_found:
                                init_teacher = ita_teacher_found
                        else:
                            init_h = 2
                        init_double = (s_id in ["ita", "mat", "tec", "art", "mot"])
    
                    # Se è teatro, assegna in automatico al docente di Lettere se non assegnato
                    if (s_id == "app_custom" or "teatro" in s_id.lower()) and init_teacher == "-- Non assegnato --" and ita_teacher_found:
                        init_teacher = ita_teacher_found
    
                    r_col1, r_col2, r_col3, r_col4 = st.columns([3, 3, 2, 2])
                    with r_col1:
                        st.markdown(f"**{s_obj.name}**")
                    with r_col2:
                        t_idx = teacher_opts.index(init_teacher) if init_teacher in teacher_opts else 0
                        chosen_t = st.selectbox(
                            f"Docente per {s_obj.name}",
                            teacher_opts,
                            index=t_idx,
                            format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x,
                            key=f"cfg_c_{sel_class_cfg}_{s_id}_t",
                            label_visibility="collapsed"
                        )
                    with r_col3:
                        chosen_h = st.number_input(
                            f"Ore {s_obj.name}",
                            min_value=0,
                            max_value=10,
                            value=init_h,
                            key=f"cfg_c_{sel_class_cfg}_{s_id}_h",
                            label_visibility="collapsed"
                        )
                    with r_col4:
                        v_pref = st.session_state.get("block_prefs_version", 0)
                        cur_d_val = problem.config.subject_block_preferences.get(s_id, False) if (hasattr(problem.config, "subject_block_preferences") and problem.config.subject_block_preferences and s_id in problem.config.subject_block_preferences) else init_double
                        chosen_d = st.checkbox(
                            "Blocco 2h 🔒",
                            value=bool(cur_d_val),
                            key=f"cfg_c_v{v_pref}_{sel_class_cfg}_{s_id}_d",
                            label_visibility="collapsed"
                        )
    
                    if chosen_h > 0:
                        new_class_data.append({
                            "subject_id": s_id,
                            "teacher_id": chosen_t if chosen_t != "-- Non assegnato --" else None,
                            "hours_per_week": chosen_h,
                            "force_double_hours": chosen_d
                        })
    
                # Totale Ore Classe Calcolato
                tot_c_hours = sum(item["hours_per_week"] for item in new_class_data)
                st.write("")
                if tot_c_hours == 30:
                    st.success(f"📊 **Totale Monte Ore Classe {c_obj.name}**: **{tot_c_hours} / 30 ore** (Perfetto al 100% ✅)")
                elif tot_c_hours < 30:
                        st.warning(f"📊 **Totale Monte Ore Classe {c_obj.name}**: **{tot_c_hours} / 30 ore** (Mancano **{30 - tot_c_hours} ore**)")
                else:
                    st.error(f"📊 **Totale Monte Ore Classe {c_obj.name}**: **{tot_c_hours} / 30 ore** (Eccesso di **+{tot_c_hours - 30} ore**)")
                    if st.button(f"⚡ Pareggia Subito a 30 Ore (Scala 1h da Italiano per fare spazio a Teatro)", key=f"fix_ita_btn_{sel_class_cfg}"):
                        st.session_state[f"cfg_c_{sel_class_cfg}_ita_h"] = 5
                        st.rerun()

                if st.button(f"💾 Salva Consiglio di Classe & Materie per {c_obj.name}", type="primary"):
                    # Rimuovi le vecchie assegnazioni di questa classe
                    problem.assignments = [a for a in problem.assignments if a.class_id != sel_class_cfg]
                    
                    # Inserisci le nuove
                    for idx_item, item in enumerate(new_class_data):
                        t_id_to_use = item["teacher_id"]
                        if t_id_to_use: # Assegna solo se un docente è stato selezionato
                            assign_id = f"a_{sel_class_cfg}_{item['subject_id']}_{t_id_to_use}_{idx_item}".lower().replace(" ", "_")
                            problem.assignments.append(TeachingAssignment(
                                id=assign_id,
                                teacher_id=t_id_to_use,
                                class_id=sel_class_cfg,
                                subject_id=item["subject_id"],
                                hours_per_week=item["hours_per_week"],
                                force_double_hours=item["force_double_hours"],
                                max_daily_hours=2
                            ))
    
                    st.success(f"Quadro materie e docenti per la classe {c_obj.name} salvato con successo!")
                    st.rerun()
        else:
            st.info("Aggiungi prima almeno una classe per poterne definire il consiglio di classe e le materie.")
    
# =============================================================
# TAB 3: BLOCCHI DA 2 E 3 ORE & PARALLELISMI DIDATTICI
# =============================================================
with tabs[2]:
    st.header("🔗 Blocchi 2h/3h & Parallelismi Didattici")
    st.caption("Configura per ciascuna materia o docente le forzature a blocchi da 2 o 3 ore consecutive e i parallelismi orari (es. palestre o classi aperte).")
    
    render_subject_coupling_panel(problem, key_prefix="tab4_blocks")
    st.divider()
    render_parallel_classes_panel(problem, key_prefix="tab4_parallels")

# =============================================================
# TAB 4: SOSTEGNO, DVA & POTENZIAMENTO
# =============================================================
with tabs[3]:
    st.header("♿ Sostegno Didattico, DVA & Potenziamento")
    render_support_management_tab(problem)
    st.write("Verifica l'allineamento delle **30 ore per classe** e la copertura delle cattedre (**18h / Part-Time**) di tutti i docenti.")

    if "editing_assign_idx" not in st.session_state:
        st.session_state.editing_assign_idx = None

    edit_a_idx = st.session_state.editing_assign_idx
    is_editing_assign = (edit_a_idx is not None and 0 <= edit_a_idx < len(problem.assignments))

    if is_editing_assign:
        target_a = problem.assignments[edit_a_idx]
        t_obj_name = problem.teachers[target_a.teacher_id].name if target_a.teacher_id in problem.teachers else target_a.teacher_id
        c_obj_name = problem.classes[target_a.class_id].name if target_a.class_id in problem.classes else target_a.class_id
        s_obj_name = problem.subjects[target_a.subject_id].name if target_a.subject_id in problem.subjects else target_a.subject_id
        assign_form_title = f"✏️ Modifica Cattedra: {t_obj_name} → {s_obj_name} ({target_a.hours_per_week}h) in {c_obj_name}"
        st.success(f"Modalità Modifica attiva per la cattedra n° {edit_a_idx + 1}. I dati sono precaricati nei campi sottostanti.")
    else:
        target_a = None
        assign_form_title = "➕ Nuova Assegnazione Cattedra"

    with st.expander(assign_form_title, expanded=is_editing_assign):
        c_a1, c_a2, c_a3 = st.columns(3)
        
        teacher_keys = list(problem.teachers.keys())
        class_keys = list(problem.classes.keys())
        subj_keys = list(problem.subjects.keys())
        
        with c_a1:
            init_t_idx = teacher_keys.index(target_a.teacher_id) if (is_editing_assign and target_a.teacher_id in teacher_keys) else 0
            init_c_idx = class_keys.index(target_a.class_id) if (is_editing_assign and target_a.class_id in class_keys) else 0
            sel_teacher = st.selectbox("Docente Titolare", teacher_keys, index=init_t_idx, format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x, key="assign_t_sel")
            sel_class = st.selectbox("Classe", class_keys, index=init_c_idx, format_func=lambda x: problem.classes[x].name if x in problem.classes else x, key="assign_c_sel")
        with c_a2:
            init_s_idx = subj_keys.index(target_a.subject_id) if (is_editing_assign and target_a.subject_id in subj_keys) else 0
            init_h = target_a.hours_per_week if is_editing_assign else 3
            sel_subj = st.selectbox("Materia", subj_keys, index=init_s_idx, format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x, key="assign_s_sel")
            sel_hours = st.number_input("Ore Settimanali", min_value=1, max_value=10, value=init_h, key="assign_h_inp")
        with c_a3:
            init_double = target_a.force_double_hours if is_editing_assign else False
            init_max_d = target_a.max_daily_hours if is_editing_assign else 2
            opt_double = st.checkbox("🔒 Richiedi Ore Doppie / Blocco da 2 ore", value=init_double, help="Incoraggia o forza lo svolgimento di 2 ore consecutive", key="assign_d_chk")
            opt_max_daily = st.number_input("Max ore giornaliere per questa materia", min_value=1, max_value=4, value=init_max_d, key="assign_md_inp")
            
            # Compresenze (fino a 4 docenti, es. Orchestra Musicale, Solfeggio, Prolungato)
            init_co_t = target_a.co_teacher_ids if is_editing_assign else []
            co_opts = [t for t in teacher_keys if t != sel_teacher]
            chosen_co_teachers = st.multiselect(
                "👥 Docenti in Compresenza (fino a 4 docenti contemporanei):",
                options=co_opts,
                default=[ct for ct in init_co_t if ct in co_opts],
                format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x,
                max_selections=4,
                key="assign_co_teachers_multisel"
            )
            
        col_asave1, col_asave2 = st.columns([2, 1])
        with col_asave1:
            save_btn_txt = "💾 Salva Modifiche Cattedra" if is_editing_assign else "💾 Assegna Cattedra"
            if st.button(save_btn_txt, type="primary", use_container_width=True):
                if is_editing_assign:
                    target_a.teacher_id = sel_teacher
                    target_a.class_id = sel_class
                    target_a.subject_id = sel_subj
                    target_a.hours_per_week = sel_hours
                    target_a.force_double_hours = opt_double
                    target_a.max_daily_hours = opt_max_daily
                    target_a.co_teacher_ids = chosen_co_teachers
                    st.session_state.editing_assign_idx = None
                    st.success("Cattedra modificata con successo!")
                else:
                    assign_id = f"a_{sel_class}_{sel_subj}_{sel_teacher}".lower().replace(" ", "_")
                    new_assign = TeachingAssignment(
                        id=assign_id,
                        teacher_id=sel_teacher,
                        class_id=sel_class,
                        subject_id=sel_subj,
                        hours_per_week=sel_hours,
                        force_double_hours=opt_double,
                        max_daily_hours=opt_max_daily,
                        co_teacher_ids=chosen_co_teachers
                    )
                    problem.assignments.append(new_assign)
                    st.success(f"Cattedra assegnata: {problem.teachers[sel_teacher].name} → {problem.subjects[sel_subj].name} ({sel_hours}h) in {problem.classes[sel_class].name}")
                st.rerun()

        with col_asave2:
            if is_editing_assign:
                if st.button("❌ Annulla Modifica", use_container_width=True):
                    st.session_state.editing_assign_idx = None
                    st.rerun()

    # -------------------------------------------------------------
    # CONTROLLI DI QUADRATURA MONTE ORE & ALERT
    # -------------------------------------------------------------
    class_hours = {c_id: 0 for c_id in problem.classes}
    for a in problem.assignments:
        if a.class_id in class_hours:
            class_hours[a.class_id] += a.hours_per_week
            
    expected_total_slots = problem.config.total_weekly_slots

    # Rilevamento discrepanze classi (rispetta monte ore per indirizzo: 30h, 32h Musicale, 36h Prolungato)
    unbalanced_classes = []
    for c_id, tot_h in class_hours.items():
        c_obj = problem.classes[c_id]
        target_cl_h = getattr(c_obj, "weekly_hours_target", expected_total_slots) or expected_total_slots
        if tot_h != target_cl_h:
            diff = target_cl_h - tot_h
            unbalanced_classes.append((c_obj.name, tot_h, target_cl_h, diff))

    # Rilevamento discrepanze docenti
    unbalanced_teachers = []
    teacher_hours_summary = []
    for t_id, t in problem.teachers.items():
        t_assigns = [a for a in problem.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
        t_sup = [sa for sa in getattr(problem, "support_assignments", []) if sa.teacher_id == t_id]
        t_enh = [ea for ea in getattr(problem, "enhancement_assignments", []) if ea.teacher_id == t_id]
        
        tot_assigned = sum(a.hours_per_week for a in t_assigns) + sum(sa.hours_per_week for sa in t_sup) + sum(ea.hours_per_week for ea in t_enh)
        
        is_pt = getattr(t, "is_part_time", False)
        target_h = getattr(t, "contract_hours", None) or (9 if is_pt else 18)
        
        role_tag = ""
        if t_sup or "sostegno" in getattr(t, "cdc", "").lower() or "admm" in getattr(t, "cdc", "").lower():
            role_tag = " [Sostegno]"
        elif t_enh or "potenziamento" in getattr(t, "cdc", "").lower():
            role_tag = " [Potenziamento]"
            
        if tot_assigned == target_h:
            status_txt = f"✅ Completa ({tot_assigned}/{target_h}h)"
        elif tot_assigned < target_h:
            diff = target_h - tot_assigned
            status_txt = f"⚠️ Incompleta ({tot_assigned}/{target_h}h: -{diff}h)"
            unbalanced_teachers.append((t.name, tot_assigned, target_h, -diff))
        else:
            diff = tot_assigned - target_h
            status_txt = f"❌ Sovraccarico ({tot_assigned}/{target_h}h: +{diff}h)"
            unbalanced_teachers.append((t.name, tot_assigned, target_h, diff))

        contratto_label = f"Part-Time (max {getattr(t, 'max_working_days', 3)} gg)" if is_pt else "Tempo Pieno (18h)"
        teacher_hours_summary.append({
            "Docente": t.name,
            "Contratto": contratto_label + role_tag,
            "Ore Assegnate": f"{tot_assigned} ore",
            "Target Contrattuale": f"{target_h} ore",
            "Stato Cattedra": status_txt
        })

    # ALERT PROMINENTI SE NON QUADRANO GLI INSERIMENTI
    if unbalanced_classes or unbalanced_teachers:
        st.error("🚨 **ALERT DI QUADRATURA: RILEVATE DISCREPANZE NEL MONTE ORE!**")
        alert_col1, alert_col2 = st.columns(2)
        with alert_col1:
            if unbalanced_classes:
                st.markdown("##### ⚠️ Classi con monte ore non allineato:")
                for c_name, tot_h, target_cl_h, diff in unbalanced_classes:
                    if diff > 0:
                        st.markdown(f"- **Classe {c_name}**: ha **{tot_h} ore** *(Mancano **{diff} ore** per arrivare a {target_cl_h}h)*")
                    else:
                        st.markdown(f"- **Classe {c_name}**: ha **{tot_h} ore** *(Supero di **{abs(diff)} ore** rispetto a {target_cl_h}h)*")
            else:
                st.success("Tutte le classi quadrano perfettamente al loro monte ore (30h/32h/36h)! ✅")

        with alert_col2:
            if unbalanced_teachers:
                st.markdown("##### ⚠️ Docenti con cattedra non allineata:")
                for t_name, tot_h, target_h, diff in unbalanced_teachers:
                    if diff < 0:
                        st.markdown(f"- **{t_name}**: ha **{tot_h}/{target_h} ore** *(Mancano **{abs(diff)} ore**)*")
                    else:
                        st.markdown(f"- **{t_name}**: ha **{tot_h}/{target_h} ore** *(Supero di **+{diff} ore**)*")
            else:
                st.success("Tutti i docenti sono perfettamente allineati al contratto! ✅")

    st.subheader(f"📋 Cattedre Attive ({len(problem.assignments)})")
    if not unbalanced_classes:
        st.success(f"✅ **Tutte le {len(problem.classes)} Classi hanno esattamente 30 / 30 ore settimanali assegnate (Monte Ore Completo al 100%)**")
        with st.expander("🔍 Visualizza Dettaglio Monte Ore per Singola Classe", expanded=False):
            cols_per_row = 6
            class_items = list(class_hours.items())
            for row_start in range(0, len(class_items), cols_per_row):
                row_items = class_items[row_start:row_start + cols_per_row]
                r_cols = st.columns(cols_per_row)
                for c_idx, (c_id, total_h) in enumerate(row_items):
                    with r_cols[c_idx]:
                        c_name = problem.classes[c_id].name
                        st.metric(f"Classe {c_name}", f"{total_h} h", delta="30h ✅")
    else:
        st.markdown("##### 🏫 Monte Ore per Classe (Target: 30 ore ciascuna)")
        cols_per_row = 6
        class_items = list(class_hours.items())
        for row_start in range(0, len(class_items), cols_per_row):
            row_items = class_items[row_start:row_start + cols_per_row]
            r_cols = st.columns(cols_per_row)
            for c_idx, (c_id, total_h) in enumerate(row_items):
                with r_cols[c_idx]:
                    c_name = problem.classes[c_id].name
                    if total_h == expected_total_slots:
                        st.metric(f"Classe {c_name}", f"{total_h} h", delta="30h ✅")
                    elif total_h < expected_total_slots:
                        st.metric(f"Classe {c_name}", f"{total_h} h", delta=f"-{expected_total_slots - total_h}h ⚠️", delta_color="inverse")
                    else:
                        st.metric(f"Classe {c_name}", f"{total_h} h", delta=f"+{total_h - expected_total_slots}h ❌", delta_color="inverse")

    st.markdown("##### 👥 Verifica Monte Ore per Docente (Cattedre a 18h & Part-Time)")
    st.dataframe(pd.DataFrame(teacher_hours_summary), use_container_width=True, hide_index=True)

    st.divider()

    st.subheader("📋 Gestione Cattedre & Desiderata Didattici")
    
    # PANNELLO SELEZIONE MULTIPLA E CANCELLAZIONE IN BLOCCO CATTEDRE
    with st.expander("🗑️ Gestione Multipla & Cancellazione in Blocco Cattedre", expanded=False):
        st.caption("Filtra e seleziona più cattedre da cancellare contemporaneamente o azzera tutte le cattedre della scuola.")
        
        c_fil1, c_fil2, c_fil3 = st.columns(3)
        with c_fil1:
            f_b_t = st.selectbox("Filtra per Docente:", ["-- Tutti --"] + list(problem.teachers.keys()), format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x, key="cattedre_batch_filter_t")
        with c_fil2:
            f_b_c = st.selectbox("Filtra per Classe:", ["-- Tutte --"] + list(problem.classes.keys()), format_func=lambda x: problem.classes[x].name if x in problem.classes else x, key="cattedre_batch_filter_c")
        with c_fil3:
            f_b_s = st.selectbox("Filtra per Materia:", ["-- Tutte --"] + list(problem.subjects.keys()), format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x, key="cattedre_batch_filter_s")

        eligible_assign_indices = []
        for idx, a in enumerate(problem.assignments):
            if f_b_t != "-- Tutti --" and a.teacher_id != f_b_t: continue
            if f_b_c != "-- Tutte --" and a.class_id != f_b_c: continue
            if f_b_s != "-- Tutte --" and a.subject_id != f_b_s: continue
            eligible_assign_indices.append(idx)

        b_act1, b_act2 = st.columns(2)
        with b_act1:
            if st.button(f"☑️ Seleziona Tutte le Cattedre Filtrate ({len(eligible_assign_indices)})", use_container_width=True, key="btn_sel_all_assigns_filt"):
                st.session_state["tab4_batch_assign_sel"] = list(eligible_assign_indices)
                st.rerun()
        with b_act2:
            if st.button("⬜ Deseleziona Tutte", use_container_width=True, key="btn_desel_all_assigns"):
                st.session_state["tab4_batch_assign_sel"] = []
                st.rerun()

        cur_assign_sel = [idx for idx in st.session_state.get("tab4_batch_assign_sel", []) if idx < len(problem.assignments)]
        chosen_batch_assigns = st.multiselect(
            "Cattedre selezionate per l'eliminazione:",
            options=list(range(len(problem.assignments))),
            default=cur_assign_sel,
            format_func=lambda x: f"N° {x+1}: {problem.classes[problem.assignments[x].class_id].name if problem.assignments[x].class_id in problem.classes else problem.assignments[x].class_id} — {problem.subjects[problem.assignments[x].subject_id].name if problem.assignments[x].subject_id in problem.subjects else problem.assignments[x].subject_id} ({problem.assignments[x].hours_per_week}h) → {problem.teachers[problem.assignments[x].teacher_id].name if problem.assignments[x].teacher_id in problem.teachers else 'Docente sconosciuto'}",
            key="tab4_batch_assign_sel_widget"
        )
        st.session_state["tab4_batch_assign_sel"] = chosen_batch_assigns

        del_col_a1, del_col_a2 = st.columns(2)
        with del_col_a1:
            if chosen_batch_assigns:
                if st.button(f"🗑️ Elimina le {len(chosen_batch_assigns)} Cattedre Selezionate", type="primary", use_container_width=True, key="btn_do_batch_del_assigns"):
                    to_remove_set = set(chosen_batch_assigns)
                    problem.assignments = [a for idx, a in enumerate(problem.assignments) if idx not in to_remove_set]
                    st.session_state["tab4_batch_assign_sel"] = []
                    st.session_state.editing_assign_idx = None
                    st.success(f"Eliminate {len(chosen_batch_assigns)} cattedre con successo!")
                    st.rerun()
            else:
                st.button("🗑️ Elimina Cattedre Selezionate (0)", disabled=True, use_container_width=True, key="btn_do_batch_del_assigns_dis")

        with del_col_a2:
            with st.popover("⚠️ Svuota / Elimina TUTTE le Cattedre", use_container_width=True):
                st.error(f"Vuoi eliminare TUTTE le {len(problem.assignments)} cattedre della scuola?")
                chk_conf_del_all_a = st.checkbox("Sì, confermo la cancellazione totale delle cattedre", key="chk_conf_del_all_assigns")
                if st.button("🚨 CONFERMA ELIMINAZIONE TOTALE CATTEDRE", type="primary", disabled=not chk_conf_del_all_a, use_container_width=True):
                    problem.assignments.clear()
                    st.session_state["tab4_batch_assign_sel"] = []
                    st.session_state.editing_assign_idx = None
                    st.success("Tutte le cattedre sono state eliminate!")
                    st.rerun()

    # SELETTORE VISTA ORDINATA
    st.write("")
    view_mode = st.radio(
        "Modalità di Visualizzazione & Modifica Cattedre:",
        [
            "👨‍🏫 Vista per Docente",
            "🏫 Vista per Classe",
            "📚 Vista per Materia / CdC",
            "📋 Tabella Generale con Filtri e Ordinamento"
        ],
        horizontal=True
    )

    # -------------------------------------------------------------
    # VISTA 1: RAGGRUPPATA PER DOCENTE
    # -------------------------------------------------------------
    if "Docente" in view_mode:
        st.markdown("##### 👨‍🏫 Cattedre e Desiderata Didattici divisi per Docente")
        st.caption("Seleziona un docente per visualizzarne e modificarne gli insegnamenti e i vincoli didattici.")
        
        doc_keys = list(problem.teachers.keys())
        if doc_keys:
            sel_view_tid = st.selectbox(
                "Scegli il Docente da ispezionare / modificare:",
                doc_keys,
                format_func=lambda x: f"{problem.teachers[x].name} ({sum(a.hours_per_week for a in problem.assignments if a.teacher_id == x)}h)",
                key="tab4_view_sel_doc"
            )
            
            t = problem.teachers[sel_view_tid]
            t_assign_list = [(idx, a) for idx, a in enumerate(problem.assignments) if a.teacher_id == sel_view_tid or sel_view_tid in a.co_teacher_ids]
            tot_h = sum(a.hours_per_week for _, a in t_assign_list)
            is_pt = getattr(t, "is_part_time", False)
            target_h = getattr(t, "contract_hours", None) or (9 if is_pt else 18)
            
            if tot_h == target_h:
                st.success(f"🟢 **{t.name}**: {tot_h}/{target_h} ore assegnate (Cattedra Completa)")
            elif tot_h < target_h:
                st.warning(f"🟠 **{t.name}**: {tot_h}/{target_h} ore assegnate (Mancano {target_h - tot_h}h)")
            else:
                st.error(f"🔴 **{t.name}**: {tot_h}/{target_h} ore assegnate (Sovraccarico di +{tot_h - target_h}h)")
                
            if t_assign_list:
                th_cols = st.columns([2, 3, 2, 2, 2, 1, 1])
                with th_cols[0]: st.markdown("**Classe**")
                with th_cols[1]: st.markdown("**Materia**")
                with th_cols[2]: st.markdown("**Ore/Sett.**")
                with th_cols[3]: st.markdown("**Ore Doppie**")
                with th_cols[4]: st.markdown("**Max Ore/Gg**")
                with th_cols[5]: st.markdown("**Mod.**")
                with th_cols[6]: st.markdown("**Elim.**")
                st.divider()

                for a_idx, a in t_assign_list:
                    c_name = problem.classes[a.class_id].name if a.class_id in problem.classes else a.class_id
                    s_name = problem.subjects[a.subject_id].name if a.subject_id in problem.subjects else a.subject_id
                    is_cur = (edit_a_idx == a_idx)
                    
                    r_cols = st.columns([2, 3, 2, 2, 2, 1, 1])
                    with r_cols[0]:
                        st.markdown(f"👉 **{c_name}**" if is_cur else f"**{c_name}**")
                    with r_cols[1]:
                        st.write(s_name)
                    with r_cols[2]:
                        st.write(f"{a.hours_per_week} ore")
                    with r_cols[3]:
                        st.caption("Blocco 2h 🔒" if a.force_double_hours else "Singole")
                    with r_cols[4]:
                        st.caption(f"Max {a.max_daily_hours}h/gg")
                    with r_cols[5]:
                        if st.button("✏️", key=f"edit_tdoc_{a_idx}", help=f"Modifica {s_name} in {c_name}"):
                            st.session_state.editing_assign_idx = a_idx
                            st.rerun()
                    with r_cols[6]:
                        if st.button("🗑️", key=f"del_tdoc_{a_idx}", help="Elimina insegnamento"):
                            del problem.assignments[a_idx]
                            if st.session_state.editing_assign_idx == a_idx:
                                st.session_state.editing_assign_idx = None
                            st.success("Insegnamento eliminato!")
                            st.rerun()
            else:
                st.info(f"Nessun insegnamento assegnato a {t.name}.")

    # -------------------------------------------------------------
    # VISTA 2: RAGGRUPPATA PER CLASSE
    # -------------------------------------------------------------
    elif "Classe" in view_mode:
        st.markdown("##### 🏫 Cattedre e Docenti divisi per Classe")
        st.caption("Seleziona una classe per verificare e modificare i docenti e le materie.")
        
        cls_keys = list(problem.classes.keys())
        if cls_keys:
            sel_view_cid = st.selectbox(
                "Scegli la Classe da ispezionare / modificare:",
                cls_keys,
                format_func=lambda x: f"Classe {problem.classes[x].name} ({sum(a.hours_per_week for a in problem.assignments if a.class_id == x)}/30h)",
                key="tab4_view_sel_cls"
            )
            
            c = problem.classes[sel_view_cid]
            c_assign_list = [(idx, a) for idx, a in enumerate(problem.assignments) if a.class_id == sel_view_cid]
            tot_h_c = sum(a.hours_per_week for _, a in c_assign_list)
            
            if tot_h_c == 30:
                st.success(f"🟢 **Classe {c.name}**: {tot_h_c}/30 ore (Quadro Completo ✅)")
            else:
                st.warning(f"🟠 **Classe {c.name}**: {tot_h_c}/30 ore")
                
            if c_assign_list:
                th_cols = st.columns([3, 3, 2, 2, 2, 1, 1])
                with th_cols[0]: st.markdown("**Materia**")
                with th_cols[1]: st.markdown("**Docente Incaricato**")
                with th_cols[2]: st.markdown("**Ore/Sett.**")
                with th_cols[3]: st.markdown("**Ore Doppie**")
                with th_cols[4]: st.markdown("**Max Ore/Gg**")
                with th_cols[5]: st.markdown("**Mod.**")
                with th_cols[6]: st.markdown("**Elim.**")
                st.divider()

                for a_idx, a in c_assign_list:
                    t_name = problem.teachers[a.teacher_id].name if a.teacher_id in problem.teachers else a.teacher_id
                    s_name = problem.subjects[a.subject_id].name if a.subject_id in problem.subjects else a.subject_id
                    
                    r_cols = st.columns([3, 3, 2, 2, 2, 1, 1])
                    with r_cols[0]: st.markdown(f"**{s_name}**")
                    with r_cols[1]: st.write(t_name)
                    with r_cols[2]: st.write(f"{a.hours_per_week} ore")
                    with r_cols[3]: st.caption("Blocco 2h 🔒" if a.force_double_hours else "Singole")
                    with r_cols[4]:
                        st.caption(f"Max {a.max_daily_hours}h/gg")
                    with r_cols[5]:
                        if st.button("✏️", key=f"edit_tcls_{a_idx}", help=f"Modifica cattedra {s_name} in {c.name}"):
                            st.session_state.editing_assign_idx = a_idx
                            st.rerun()
                    with r_cols[6]:
                        if st.button("🗑️", key=f"del_tcls_{a_idx}", help="Elimina insegnamento"):
                            del problem.assignments[a_idx]
                            if st.session_state.editing_assign_idx == a_idx:
                                st.session_state.editing_assign_idx = None
                            st.success("Insegnamento eliminato!")
                            st.rerun()
            else:
                st.info(f"Nessun insegnamento assegnato alla classe {c.name}.")

    # -------------------------------------------------------------
    # VISTA 3: RAGGRUPPATA PER MATERIA / CDC
    # -------------------------------------------------------------
    elif "Materia" in view_mode:
        st.markdown("##### 📚 Cattedre e Docenti divisi per Disciplina / CdC")
        st.caption("Seleziona una materia per verificarne la copertura in tutte le sezioni.")
        
        subj_keys = list(problem.subjects.keys())
        if subj_keys:
            sel_view_sid = st.selectbox(
                "Scegli la Materia da ispezionare / modificare:",
                subj_keys,
                format_func=lambda x: f"{problem.subjects[x].name} ({sum(a.hours_per_week for a in problem.assignments if a.subject_id == x)}h totali)",
                key="tab4_view_sel_subj"
            )
            
            s = problem.subjects[sel_view_sid]
            s_assign_list = [(idx, a) for idx, a in enumerate(problem.assignments) if a.subject_id == sel_view_sid]
            tot_h_s = sum(a.hours_per_week for _, a in s_assign_list)
            
            st.info(f"📘 **{s.name}**: {tot_h_s} ore settimanali complessive assegnate su {len(s_assign_list)} classi.")
            
            if s_assign_list:
                th_cols = st.columns([2, 3, 2, 2, 2, 1, 1])
                with th_cols[0]: st.markdown("**Classe**")
                with th_cols[1]: st.markdown("**Docente Incaricato**")
                with th_cols[2]: st.markdown("**Ore/Sett.**")
                with th_cols[3]: st.markdown("**Ore Doppie**")
                with th_cols[4]: st.markdown("**Max Ore/Gg**")
                with th_cols[5]: st.markdown("**Mod.**")
                with th_cols[6]: st.markdown("**Elim.**")
                st.divider()

                for a_idx, a in s_assign_list:
                    c_name = problem.classes[a.class_id].name if a.class_id in problem.classes else a.class_id
                    t_name = problem.teachers[a.teacher_id].name if a.teacher_id in problem.teachers else a.teacher_id
                    
                    r_cols = st.columns([2, 3, 2, 2, 2, 1, 1])
                    with r_cols[0]: st.markdown(f"**Classe {c_name}**")
                    with r_cols[1]: st.write(t_name)
                    with r_cols[2]: st.write(f"{a.hours_per_week} ore")
                    with r_cols[3]: st.caption("Blocco 2h 🔒" if a.force_double_hours else "Singole")
                    with r_cols[4]:
                        st.caption(f"Max {a.max_daily_hours}h/gg")
                    with r_cols[5]:
                        if st.button("✏️", key=f"edit_tsubj_{a_idx}", help=f"Modifica {s.name} in {c_name}"):
                            st.session_state.editing_assign_idx = a_idx
                            st.rerun()
                    with r_cols[6]:
                        if st.button("🗑️", key=f"del_tsubj_{a_idx}", help="Elimina insegnamento"):
                            del problem.assignments[a_idx]
                            if st.session_state.editing_assign_idx == a_idx:
                                st.session_state.editing_assign_idx = None
                            st.success("Insegnamento eliminato!")
                            st.rerun()
            else:
                st.info(f"Nessuna cattedra assegnata per la materia {s.name}.")

    # -------------------------------------------------------------
    # VISTA 4: TABELLA GENERALE COMPLETA CON FILTRI E ORDINAMENTO
    # -------------------------------------------------------------
    else:
        st.markdown("##### 📋 Tabella Generale Cattedre & Assegnazioni")
        st.caption("Filtra e ordina l'elenco completo di tutti gli insegnamenti della scuola.")
        
        # Filtri e Ordinamento
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        with f_col1:
            filter_teacher = st.selectbox("Filtra per Docente:", ["-- Tutti i Docenti --"] + list(problem.teachers.keys()), format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x)
        with f_col2:
            filter_class = st.selectbox("Filtra per Classe:", ["-- Tutte le Classi --"] + list(problem.classes.keys()), format_func=lambda x: problem.classes[x].name if x in problem.classes else x)
        with f_col3:
            filter_subj = st.selectbox("Filtra per Materia:", ["-- Tutte le Materie --"] + list(problem.subjects.keys()), format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x)
        with f_col4:
            order_by = st.selectbox("Ordina per:", ["Docente", "Classe", "Materia", "Ore Decrescenti"])

        # Costruzione e filtraggio
        filtered_assigns = [(idx, a) for idx, a in enumerate(problem.assignments)]
        if filter_teacher != "-- Tutti i Docenti --":
            filtered_assigns = [(idx, a) for idx, a in filtered_assigns if a.teacher_id == filter_teacher]
        if filter_class != "-- Tutte le Classi --":
            filtered_assigns = [(idx, a) for idx, a in filtered_assigns if a.class_id == filter_class]
        if filter_subj != "-- Tutte le Materie --":
            filtered_assigns = [(idx, a) for idx, a in filtered_assigns if a.subject_id == filter_subj]

        # Ordinamento
        if order_by == "Docente":
            filtered_assigns.sort(key=lambda x: problem.teachers[x[1].teacher_id].name if x[1].teacher_id in problem.teachers else "")
        elif order_by == "Classe":
            filtered_assigns.sort(key=lambda x: problem.classes[x[1].class_id].name if x[1].class_id in problem.classes else "")
        elif order_by == "Materia":
            filtered_assigns.sort(key=lambda x: problem.subjects[x[1].subject_id].name if x[1].subject_id in problem.subjects else "")
        elif order_by == "Ore Decrescenti":
            filtered_assigns.sort(key=lambda x: x[1].hours_per_week, reverse=True)

        st.caption(f"Visualizzati **{len(filtered_assigns)}** insegnamenti su **{len(problem.assignments)}** totali.")
        
        tab_df_data = []
        for a_idx, a in filtered_assigns:
            tab_df_data.append({
                "N°": a_idx + 1,
                "Classe": problem.classes[a.class_id].name if a.class_id in problem.classes else a.class_id,
                "Materia": problem.subjects[a.subject_id].name if a.subject_id in problem.subjects else a.subject_id,
                "Docente": problem.teachers[a.teacher_id].name if a.teacher_id in problem.teachers else a.teacher_id,
                "Ore/Settimana": f"{a.hours_per_week}h",
                "Blocco 2h": "Sì 🔒" if a.force_double_hours else "No (Singole)",
                "Max Ore/Giorno": f"{a.max_daily_hours}h"
            })
            
        st.dataframe(pd.DataFrame(tab_df_data), use_container_width=True, hide_index=True)
        
        # Modifica / Eliminazione Rapida per Indice
        st.write("")
        c_quick1, c_quick2, c_quick3 = st.columns([2, 1, 1])
        with c_quick1:
            sel_quick_idx = st.selectbox(
                "Seleziona insegnamento da modificare o eliminare:",
                [idx for idx, _ in filtered_assigns],
                format_func=lambda x: f"N° {x+1}: {problem.teachers[problem.assignments[x].teacher_id].name if problem.assignments[x].teacher_id in problem.teachers else ''} → {problem.subjects[problem.assignments[x].subject_id].name if problem.assignments[x].subject_id in problem.subjects else ''} ({problem.classes[problem.assignments[x].class_id].name if problem.assignments[x].class_id in problem.classes else ''})",
                key="tab4_quick_assign_sel"
            )
        with c_quick2:
            st.write("")
            if st.button("✏️ Modifica", use_container_width=True, key="quick_edit_assign_btn"):
                st.session_state.editing_assign_idx = sel_quick_idx
                st.rerun()
        with c_quick3:
            st.write("")
            if st.button("🗑️ Elimina", use_container_width=True, key="quick_del_assign_btn"):
                del problem.assignments[sel_quick_idx]
                if st.session_state.editing_assign_idx == sel_quick_idx:
                    st.session_state.editing_assign_idx = None
                st.success("Cattedra eliminata!")
                st.rerun()

# =============================================================
# TAB 5: GENERA ORARIO
# =============================================================
with tabs[4]:
    st.header("🚀 Generazione Automatica dell'Orario Scolastico")
    st.write(f"Solutore attivo per: **{problem.config.school_name}** ({'Modello DADA' if problem.config.is_dada else 'Modello Tradizionale'}).")

    # Controllo quadratura preventivo
    t_unbal = []
    for t_id, t in problem.teachers.items():
        tot_a = (
            sum(a.hours_per_week for a in problem.assignments if a.teacher_id == t_id) +
            sum(sa.hours_per_week for sa in getattr(problem, "support_assignments", []) if sa.teacher_id == t_id) +
            sum(ea.hours_per_week for ea in getattr(problem, "enhancement_assignments", []) if ea.teacher_id == t_id)
        )
        target = getattr(t, "contract_hours", None) or (9 if getattr(t, "is_part_time", False) else 18)
        if tot_a != target:
            t_unbal.append((t.name, tot_a, target))
            
    c_unbal = []
    exp_slots = problem.config.total_weekly_slots
    for c_id, c in problem.classes.items():
        tot_c = sum(a.hours_per_week for a in problem.assignments if a.class_id == c_id)
        target_c = getattr(c, "weekly_hours_target", exp_slots) or exp_slots
        if tot_c != target_c:
            c_unbal.append((c.name, tot_c, target_c))

    if c_unbal:
        st.warning(f"⚖️ **Nota di Quadratura**: {len(c_unbal)} classi hanno un monte ore differente dal target previsto ({c_unbal[0][1]}h invece di {c_unbal[0][2]}h per {c_unbal[0][0]}).")

    # Controllo e Risoluzione Guidata Colli di Bottiglia Aule / Laboratori
    render_room_bottlenecks_resolver(problem, key_suffix="tab5_precheck")

    if "solver_seed" not in st.session_state:
        st.session_state.solver_seed = 42

    render_optimization_criteria_panel(problem, key_prefix="tab5")
    
    st.write("")
    st.markdown("##### ⏱️ Parametri di Esecuzione & Calcolo Intelligente")
    
    # Calcolo dinamico del tempo di ottimizzazione raccomandato
    num_c_tot = len(problem.classes)
    cur_target_gaps = int(st.session_state.get("tab5_slider_max_gaps", problem.config.optimization_criteria.max_gap_limit))
    cur_strict_gaps = bool(st.session_state.get("tab5_chk_strict_gaps", problem.config.optimization_criteria.strict_gap_limit))
    
    calc_rec_time = 30
    if num_c_tot >= 12: calc_rec_time = 45
    if num_c_tot >= 18: calc_rec_time = 60
    if cur_target_gaps <= 2: calc_rec_time = max(calc_rec_time, 75 if num_c_tot >= 18 else 50)
    if cur_target_gaps <= 1: calc_rec_time = max(calc_rec_time, 90 if num_c_tot >= 18 else 60)
    if problem.config.is_dada: calc_rec_time += 15
    if cur_strict_gaps: calc_rec_time += 15
    calc_rec_time = min(240, max(20, calc_rec_time))

    if "tab5_slider_solve_time" not in st.session_state:
        st.session_state["tab5_slider_solve_time"] = calc_rec_time

    c_rec_msg, c_rec_btn = st.columns([3, 1])
    with c_rec_msg:
        st.info(f"💡 **Suggerimento Automatico**: Per **{num_c_tot} Classi** con tetto buche a **≤ {cur_target_gaps}h**{' (Modello DADA)' if problem.config.is_dada else ''}, il tempo ideale per consentire al motore di scambiare le combinazioni e compattare tutte le cattedre è **{calc_rec_time} secondi**.")
    with c_rec_btn:
        st.write("")
        if st.button(f"⚡ Usa {calc_rec_time}s Consigliati", use_container_width=True, help=f"Imposta lo slider a {calc_rec_time}s per ottenere il massimo della compattezza"):
            st.session_state["tab5_slider_solve_time"] = calc_rec_time
            st.rerun()

    c_opt1, c_opt2 = st.columns([3, 1])
    with c_opt1:
        max_solve_time = st.slider(
            "Tempo di Ottimizzazione OR-Tools (secondi)",
            min_value=15,
            max_value=300,
            value=st.session_state["tab5_slider_solve_time"],
            step=5,
            key="tab5_slider_solve_time_widget",
            help="OR-Tools CP-SAT esplora l'albero combinatorio. Più secondi concedi al motore (specie con tetto a 2h su 18 classi), più ondate di Large Neighborhood Search può eseguire per azzerare le buche residue!"
        )
        st.session_state["tab5_slider_solve_time"] = max_solve_time
    with c_opt2:
        st.write("")
        st.write(f"🎲 **Seed Ricerca**: `{st.session_state.solver_seed}`")

    c_g1, c_g2 = st.columns(2)
    with c_g1:
        btn_solve = st.button("⚡ Avvia Formulazione Orario", type="primary", use_container_width=True)
    with c_g2:
        btn_resolve = st.button("🔁 Ricalcola / Cerca Orario Alternativo", use_container_width=True, help="Esplora un ramo diverso dell'albero di ricerca per trovare una combinazione alternativa con distribuzione differente.")

    trigger_solve = False
    if btn_solve:
        trigger_solve = True
    elif btn_resolve:
        st.session_state.solver_seed += 13
        trigger_solve = True

    if trigger_solve:
        if not problem.assignments:
            st.error("Nessuna cattedra configurata! Inserisci le cattedre o ricarica la demo.")
        else:
            # 1. AUTO-COMPENSAZIONE AUTOMATICA PREVENTIVA:
            # Assicura 2 spazi teatro dedicati
            if "app_custom" in problem.subjects or any(a.subject_id == "app_custom" for a in problem.assignments):
                if "aula_teatro_1" not in problem.rooms:
                    problem.rooms["aula_teatro_1"] = Classroom(id="aula_teatro_1", name="Spazio Teatro 1 (Palcoscenico)", subject_ids=["app_custom"], capacity=1, is_special_lab=True)
                if "aula_teatro_2" not in problem.rooms:
                    problem.rooms["aula_teatro_2"] = Classroom(id="aula_teatro_2", name="Spazio Teatro 2 (Laboratorio Espressivo)", subject_ids=["app_custom"], capacity=1, is_special_lab=True)
                if "aula_teatro" in problem.rooms:
                    del problem.rooms["aula_teatro"]

                # Sincronizza Italiano a 5h per tutte le classi che hanno Teatro
                for a in problem.assignments:
                    if a.subject_id == "ita" and a.hours_per_week == 6:
                        if any(other.class_id == a.class_id and other.subject_id == "app_custom" for other in problem.assignments):
                            a.hours_per_week = 5

            # Assicura che ogni classe abbia esattamente le ore del suo indirizzo (30h, 32h Musicale, 36h Prolungato)
            exp_slots = problem.config.total_weekly_slots
            for c_id, c in problem.classes.items():
                target_c_h = getattr(c, "weekly_hours_target", exp_slots) or exp_slots
                c_assigns = [a for a in problem.assignments if a.class_id == c_id]
                tot_c = sum(a.hours_per_week for a in c_assigns)
                if tot_c > target_c_h:
                    excess = tot_c - target_c_h
                    for a in c_assigns:
                        if a.subject_id == "ita" and a.hours_per_week > 5 and excess > 0:
                            a.hours_per_week -= 1
                            excess -= 1

            opt_crit = problem.config.optimization_criteria
            user_max_gaps = int(st.session_state.get("tab5_slider_max_gaps", opt_crit.max_gap_limit))
            user_strict = bool(st.session_state.get("tab5_chk_strict_gaps", opt_crit.strict_gap_limit))
            opt_crit.max_gap_limit = user_max_gaps
            opt_crit.strict_gap_limit = user_strict

            solver = TimetableSolver(
                problem, 
                max_gap_limit=user_max_gaps, 
                strict_gap_limit=user_strict
            )
            
            # Barra di scorrimento del tempo colorata in tempo reale
            from concurrent.futures import ThreadPoolExecutor
            
            progress_container = st.empty()

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    solver.solve, 
                    max_time_seconds=max_solve_time, 
                    random_seed=st.session_state.solver_seed
                )
                
                start_calc_t = time.time()
                while not future.done():
                    elapsed = time.time() - start_calc_t
                    pct = min(0.99, max(0.01, elapsed / max(max_solve_time, 1)))
                    pct_int = int(pct * 100)
                    remaining = max(0, int(max_solve_time - elapsed))
                    
                    if elapsed < 2:
                        phase_desc = "🔍 Fase 1: Verifica incastri e rispetto vincoli rigidi (blocchi 2h, presenze, aule)"
                        color_grad = "linear-gradient(90deg, #38bdf8 0%, #2563eb 100%)"
                        badge_color = "#0284c7"
                    elif elapsed < max_solve_time * 0.35:
                        phase_desc = "🏖️ Fase 2: Massimizzazione giorni liberi docenti e ingressi posticipati"
                        color_grad = "linear-gradient(90deg, #2563eb 0%, #7c3aed 100%)"
                        badge_color = "#6d28d9"
                    elif elapsed < max_solve_time * 0.75:
                        phase_desc = "📉 Fase 3: Abbattimento ore buche ed equità carichi di lavoro"
                        color_grad = "linear-gradient(90deg, #7c3aed 0%, #db2777 50%, #f59e0b 100%)"
                        badge_color = "#be185d"
                    else:
                        phase_desc = "✨ Fase 4: Rifinitura finale e consolidamento delle cattedre"
                        color_grad = "linear-gradient(90deg, #10b981 0%, #059669 100%)"
                        badge_color = "#047857"
                    
                    import textwrap
                    custom_html = textwrap.dedent(f"""
                    <div style="background: #ffffff; border: 2px solid {badge_color}33; border-radius: 14px; padding: 20px; margin: 15px 0; box-shadow: 0 8px 25px rgba(0,0,0,0.08);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="font-weight: 800; font-size: 1.1rem; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                                <span style="font-size: 1.3rem;">⚡</span>
                                <span>Formulazione & Ottimizzazione Orario in Corso...</span>
                            </div>
                            <div style="background: {badge_color}; color: #ffffff; padding: 5px 14px; border-radius: 20px; font-weight: 800; font-size: 1.05rem; font-family: monospace; box-shadow: 0 2px 6px {badge_color}66;">
                                {pct_int}%
                            </div>
                        </div>
                        <div style="width: 100%; height: 26px; background-color: #f1f5f9; border-radius: 13px; overflow: hidden; border: 1px solid #cbd5e1; box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);">
                            <div style="width: {pct_int}%; height: 100%; background: {color_grad}; border-radius: 13px; transition: width 0.3s ease-in-out; display: flex; align-items: center; justify-content: flex-end; padding-right: 10px; color: white; font-weight: 800; font-size: 0.85rem; text-shadow: 0 1px 2px rgba(0,0,0,0.4); box-shadow: 0 0 12px {badge_color}88;">
                                {f"{pct_int}%" if pct_int >= 12 else ""}
                            </div>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 12px; font-size: 0.9rem; color: #334155;">
                            <div>
                                ⏱️ <b>Trascorsi:</b> <span style="color: #0f172a; font-weight: 700;">{int(elapsed)}s</span> / {max_solve_time}s &nbsp;|&nbsp; ⏳ <b>Rimanenti:</b> <span style="color: #0f172a; font-weight: 700;">~{remaining}s</span>
                            </div>
                            <div style="font-weight: 700; color: {badge_color};">
                                {phase_desc}
                            </div>
                        </div>
                    </div>
                    """).strip()
                    
                    if hasattr(progress_container, "html"):
                        progress_container.html(custom_html)
                    else:
                        progress_container.markdown(custom_html, unsafe_allow_html=True)
                    time.sleep(0.35)
                
                result = future.result()
                if result.status in ["OPTIMAL", "FEASIBLE"]:
                    complete_html = textwrap.dedent(f"""
                    <div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 14px; padding: 20px; margin: 15px 0; box-shadow: 0 8px 25px rgba(16, 185, 129, 0.15);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="font-weight: 800; font-size: 1.15rem; color: #065f46; display: flex; align-items: center; gap: 8px;">
                                <span>🎉</span>
                                <span>Orario Calcolato e Ottimizzato con Successo in {result.solve_time} secondi!</span>
                            </div>
                            <div style="background: #10b981; color: #ffffff; padding: 5px 14px; border-radius: 20px; font-weight: 800; font-size: 1.05rem; font-family: monospace;">
                                100%
                            </div>
                        </div>
                    </div>
                    """).strip()
                else:
                    complete_html = textwrap.dedent(f"""
                    <div style="background: #fef2f2; border: 2px solid #ef4444; border-radius: 14px; padding: 20px; margin: 15px 0; box-shadow: 0 8px 25px rgba(239, 68, 68, 0.15);">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div style="font-weight: 800; font-size: 1.15rem; color: #991b1b; display: flex; align-items: center; gap: 8px;">
                                <span>❌</span>
                                <span>Ricerca Interrotta (Stato: {result.status}) in {result.solve_time} secondi</span>
                            </div>
                            <div style="background: #ef4444; color: #ffffff; padding: 5px 14px; border-radius: 20px; font-weight: 800; font-size: 1.05rem; font-family: monospace;">
                                100%
                            </div>
                        </div>
                    </div>
                    """).strip()

                if hasattr(progress_container, "html"):
                    progress_container.html(complete_html)
                else:
                    progress_container.markdown(complete_html, unsafe_allow_html=True)
                st.session_state.result = result
                time.sleep(0.8)
                
            if result.status in ["OPTIMAL", "FEASIBLE"]:
                actual_max_gaps = max(result.gaps_by_teacher.values()) if result.gaps_by_teacher else 0
                tot_gaps_count = result.total_gap_hours
                st.success(
                    f"🎉 **Orario generato con successo in {result.solve_time} secondi!** (Stato: `{result.status}`)\n\n"
                    f"🎯 **Tetto ore buche impostato**: **≤ {user_max_gaps}h per docente** | 📊 **Max effettivo riscontrato tra tutti i docenti**: **{actual_max_gaps}h** "
                    f"(Totale ore buche dell'intero istituto: **{tot_gaps_count}h**, Equità applicata ✅)"
                )
            else:
                st.error(f"❌ **Impossibile formulare l'orario completo** (Stato del solutore: `{result.status}`).")
                if result.log_messages:
                    st.markdown("##### 🔍 Diagnosi dei Conflitti Rilevati nei Dati:")
                    for msg in result.log_messages:
                        st.markdown(f"- {msg}")
                else:
                    st.info("💡 **Suggerimenti per risolvere velocemente**:\n- Aumenta il tempo di ottimizzazione (es. a 300s nello slider sopra).\n- Alza il limite massimo di ore buca per fornire maggiore flessibilità al motore di calcolo.")
                
                render_room_bottlenecks_resolver(problem, key_suffix="tab5_fail")

    res: Optional[TimetableResult] = st.session_state.get("result")
    if res and res.status in ["OPTIMAL", "FEASIBLE"]:
        st.divider()
        st.subheader("📊 Metriche di Qualità & Desiderata Soddisfatti")
        
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        with m_col1:
            pct_fd1 = round((res.free_days_satisfied_first / res.free_days_total_first * 100)) if res.free_days_total_first > 0 else 100
            st.metric("Giorno Libero (1ª Scelta)", f"{res.free_days_satisfied_first} / {res.free_days_total_first}", delta=f"{pct_fd1}% soddisfatti")
            
        with m_col2:
            pct_fd2 = round((res.free_days_satisfied_second / res.free_days_total_second * 100)) if res.free_days_total_second > 0 else 100
            st.metric("Giorno Libero (2ª Scelta)", f"{res.free_days_satisfied_second} / {res.free_days_total_second}", delta=f"{pct_fd2}% soddisfatti")
            
        with m_col3:
            pct_double = round((res.double_hours_satisfied / res.double_hours_total * 100)) if res.double_hours_total > 0 else 100
            st.metric("Ore Doppie Didattiche", f"{res.double_hours_satisfied} / {res.double_hours_total}", delta=f"{pct_double}% soddisfatte")
            
        with m_col4:
            st.metric("Totale Ore Buche (Docenti)", f"{res.total_gap_hours} ore", delta="Minimizzate", delta_color="inverse")

        # Dettaglio per materia accorpata (flaggate vs non flaggate nel Tab 1)
        sub_blocks_info = getattr(res, "double_hours_by_subject", {})
        teacher_blocks_info = getattr(res, "double_hours_by_teacher", {})
        
        if sub_blocks_info or teacher_blocks_info:
            st.markdown("##### 🔗 Dettaglio Accorpamento Discipline & Docenti (Blocchi da 2 Ore Consecutive)")
            flagged_items = [v for v in sub_blocks_info.values() if v.get("is_flagged")] if sub_blocks_info else []
            unflagged_items = [v for v in sub_blocks_info.values() if not v.get("is_flagged")] if sub_blocks_info else []
            
            dc1, dc2 = st.columns(2)
            with dc1:
                st.markdown("**🔒 Materie Flaggate a livello di Istituto:**")
                if flagged_items:
                    for f_item in flagged_items:
                        s_name = f_item['name']
                        s_sat = f_item['satisfied']
                        s_tot = f_item['total']
                        s_pct = f_item['pct']
                        if s_sat == s_tot:
                            st.write(f"- ✅ **{s_name}**: **{s_sat} / {s_tot} classi** in blocco da 2h consecutive ({s_pct}% soddisfatto)")
                        else:
                            st.write(f"- 🟡 **{s_name}**: **{s_sat} / {s_tot} classi** in blocco da 2h consecutive ({s_pct}% soddisfatto)")
                    
                    trip_tot = getattr(res, "triple_hours_total", 0)
                    trip_sat = getattr(res, "triple_hours_satisfied", 0)
                    trip_pct = getattr(res, "triple_hours_pct", 100)
                    if trip_tot > 0:
                        if trip_sat == trip_tot:
                            st.write(f"- ✅ **Italiano (Blocco da 3h - Tema)**: **{trip_sat} / {trip_tot} classi** in blocco da 3h consecutive ({trip_pct}% soddisfatto)")
                        else:
                            st.write(f"- 🟡 **Italiano (Blocco da 3h - Tema)**: **{trip_sat} / {trip_tot} classi** in blocco da 3h consecutive ({trip_pct}% soddisfatto)")
                else:
                    st.caption("Nessuna materia flaggata per l'accorpamento a 2 ore a livello di istituto.")
                    
            with dc2:
                st.markdown("**🔓 Materie NON Flaggate (Ore Singole Separate):**")
                if unflagged_items:
                    for u_item in unflagged_items:
                        st.write(f"- ℹ️ **{u_item['name']}**: suddivisa ad ore singole su giorni diversi (1h al giorno)")
                else:
                    st.caption("Tutte le materie da 2h+ sono state flaggate come accorpate.")

            # Sezione specifica per Doppie Ore Forzate per Singolo Docente
            if teacher_blocks_info:
                st.markdown("##### 👤 Doppie Ore Forzate per Docente Singolo")
                t_cols = st.columns(min(len(teacher_blocks_info), 3) if len(teacher_blocks_info) > 0 else 1)
                for idx_tb, (tb_tid, tb_data) in enumerate(teacher_blocks_info.items()):
                    col_target = t_cols[idx_tb % len(t_cols)]
                    with col_target:
                        with st.container(border=True):
                            tb_name = tb_data["name"]
                            tb_cdc = f"[{tb_data['cdc']}] " if tb_data.get("cdc") else ""
                            tb_sat = tb_data["satisfied"]
                            tb_tot = tb_data["total"]
                            tb_pct = tb_data["pct"]
                            
                            badge = "🟢 100%" if tb_pct == 100 else f"🟡 {tb_pct}%"
                            st.markdown(f"**👤 {tb_cdc}{tb_name}** — {badge}")
                            st.write(f"**{tb_sat} / {tb_tot} cattedre** in blocco da 2h consecutive")
                            
                            for det in tb_data.get("details", []):
                                c_sat_icon = "✅" if det["is_satisfied"] else "❌"
                                st.caption(f"{c_sat_icon} **Classe {det['class_name']}** - {det['subject_name']} ({det['hours_per_week']}h)")

        # Seconda riga metriche per desiderata orari avanzati
        late_tot = getattr(res, "late_entry_total", 0)
        late_sat = getattr(res, "late_entry_satisfied", 0)
        early_tot = getattr(res, "early_exit_total", 0)
        early_sat = getattr(res, "early_exit_satisfied", 0)
        soft_tot = getattr(res, "soft_slots_total", 0)
        soft_sat = getattr(res, "soft_slots_satisfied", 0)

        if late_tot > 0 or early_tot > 0 or soft_tot > 0:
            st.markdown("##### 🎯 Rispetto Desiderata Orari Specifici")
            d_col1, d_col2, d_col3 = st.columns(3)
            with d_col1:
                if late_tot > 0:
                    pct_late = round((late_sat / late_tot * 100))
                    st.metric("🌅 Ingressi Posticipati (No 1ª ora)", f"{late_sat} / {late_tot} gg", delta=f"{pct_late}% concessi")
                else:
                    st.metric("🌅 Ingressi Posticipati", "Nessuna richiesta")

            with d_col2:
                if early_tot > 0:
                    pct_early = round((early_sat / early_tot * 100))
                    st.metric("🌇 Uscite Anticipate (No ult. ora)", f"{early_sat} / {early_tot} gg", delta=f"{pct_early}% concessi")
                else:
                    st.metric("🌇 Uscite Anticipate", "Nessuna richiesta")

            with d_col3:
                if soft_tot > 0:
                    pct_soft = round((soft_sat / soft_tot * 100))
                    st.metric("🟡 Slot Sconsigliati Evitati", f"{soft_sat} / {soft_tot}", delta=f"{pct_soft}% rispettati")
                else:
                    st.metric("🟡 Slot Sconsigliati", "Nessuna richiesta")

        # -------------------------------------------------------------
        # REPORT CLASSI APERTE & PARALLELISMI DIDATTICI
        # -------------------------------------------------------------
        active_pgs = [pg for pg in getattr(problem.config, "parallel_groups", []) if pg.is_active]
        if active_pgs:
            st.divider()
            st.subheader(f"👥 Report Classi Aperte & Parallelismi Didattici ({len(active_pgs)} Regole Attive)")
            st.caption("Verifica della corretta collocazione oraria, sincronizzazione in contemporanea e assegnazione spazi per le classi aperte.")
            
            for grp in active_pgs:
                s_name = problem.subjects[grp.subject_id].name if grp.subject_id in problem.subjects else grp.subject_id
                cl_names = [problem.classes[c].name for c in grp.class_ids if c in problem.classes]
                
                # Trova dove sono state collocate le ore in parallelo
                sync_slots = []
                for d in range(problem.config.num_days):
                    for h in range(problem.config.daily_hours[d]):
                        c_slots = [res.grid_by_class.get(c, [])[d][h] for c in grp.class_ids if c in res.grid_by_class]
                        if len(c_slots) == len(grp.class_ids) and all(sl is not None and sl.subject_id == grp.subject_id for sl in c_slots):
                            d_name = problem.config.active_days[d]
                            r_names = list(dict.fromkeys([sl.room_name for sl in c_slots if sl.room_name]))
                            t_names = list(dict.fromkeys([sl.teacher_name for sl in c_slots if sl.teacher_name]))
                            sync_slots.append((d_name, h + 1, r_names, t_names))
                
                with st.container():
                    col_p1, col_p2 = st.columns([3, 2])
                    with col_p1:
                        st.markdown(f"**🟢 {grp.name}**")
                        st.write(f"📚 Materia: **{s_name}** | 🏫 Classi: **{', '.join(cl_names)}**")
                        if grp.room_id and grp.room_id in problem.rooms:
                            st.caption(f"🏢 Spazio Condiviso Richiesto: **{problem.rooms[grp.room_id].name}**")
                    with col_p2:
                        if sync_slots:
                            slot_desc = []
                            for d_n, h_n, r_n, t_n in sync_slots:
                                r_str = f" in {', '.join(r_n)}" if r_n else ""
                                slot_desc.append(f"**{d_n} {h_n}ª Ora**{r_str}")
                            st.success(f"✅ **Sincronizzato ({len(sync_slots)}h / {grp.parallel_hours}h)**:\n" + ", ".join(slot_desc))
                            all_t = list(dict.fromkeys([t for _, _, _, t_list in sync_slots for t in t_list]))
                            if all_t:
                                st.caption(f"Docenti coinvolti: {', '.join(all_t)}")
                        else:
                            st.warning("⚠️ Ore sincronizzate non rilevate o parzialmente disallineate.")
                    st.markdown("<hr style='margin: 6px 0 12px 0;'>", unsafe_allow_html=True)

        # -------------------------------------------------------------
        # REPORT ANALITICO PER DOCENTE: "CHI HO SODDISFATTO E CHI NO"
        # -------------------------------------------------------------
        st.divider()
        st.subheader("👥 Report Analitico per Docente: Chi ho soddisfatto e chi no")
        st.caption("Verifica punto per punto quali desiderata (giorno libero, orari di ingresso/uscita, ore buche, blocchi doppi) sono stati accolti per ciascun insegnante.")

        t_reports = getattr(res, "teacher_reports", {})
        # Escludi i docenti di solo sostegno/potenziamento dal report curricolare classico
        curricular_t_ids = {a.teacher_id for a in problem.assignments}
        t_reports = {t_id: rep for t_id, rep in t_reports.items() if t_id in curricular_t_ids}
        if t_reports:
            # Filtri veloci
            f_col1, f_col2 = st.columns([2, 1])
            with f_col1:
                search_doc = st.text_input("🔍 Cerca docente per nome o classe di concorso:", key="tab5_search_doc_rep", placeholder="es. Bianchi o Lettere")
            with f_col2:
                filter_status = st.selectbox(
                    "Filtra per esito:",
                    ["Tutti i Docenti", "Solo Soddisfatti al 100% 🟢", "Con Desiderata Parziali 🟡", "Con Criticità 🔴", "Solo Part-Time"],
                    key="tab5_filter_status_doc"
                )

            summary_table = []
            for t_id, rep in t_reports.items():
                # Applicazione filtri
                if search_doc:
                    s_low = search_doc.lower()
                    if s_low not in rep["name"].lower() and s_low not in rep["cdc"].lower():
                        continue
                if filter_status == "Solo Soddisfatti al 100% 🟢" and rep["score_percent"] < 100:
                    continue
                if filter_status == "Con Desiderata Parziali 🟡" and (rep["score_percent"] < 70 or rep["score_percent"] == 100):
                    continue
                if filter_status == "Con Criticità 🔴" and rep["score_percent"] >= 70:
                    continue
                if filter_status == "Solo Part-Time" and not rep["is_part_time"]:
                    continue

                cdc_label = f"[{rep['cdc']}] " if rep["cdc"] else ""
                
                # Formattazione ore buche
                gaps_val = rep["gap_hours"]
                if gaps_val == 0:
                    gaps_disp = "0 buche 🟢"
                elif gaps_val <= 2:
                    gaps_disp = f"{gaps_val} buche 🟡"
                else:
                    gaps_disp = f"{gaps_val} buche 🔴"

                summary_table.append({
                    "Docente": f"{cdc_label}{rep['name']}",
                    "Contratto": f"Part-Time ({rep['working_days_count']} gg)" if rep["is_part_time"] else "Tempo Pieno (18h)",
                    "Giorno Libero": rep["free_day_status"],
                    "Entra Tardi": rep["late_entry_result"],
                    "Esce Presto": rep["early_exit_result"],
                    "Ore Buche": gaps_disp,
                    "Slot Sconsigliati": rep["soft_slots_result"],
                    "Ore Doppie": rep["double_hours_result"],
                    "Indice Soddisfazione": f"{rep['score_percent']}%",
                    "Valutazione": rep["status_badge"]
                })

            if summary_table:
                st.dataframe(pd.DataFrame(summary_table), use_container_width=True, hide_index=True)
            else:
                st.info("Nessun docente corrisponde ai criteri di filtro selezionati.")

            # Schede Dettagliate per Docente
            with st.expander("🔍 Esamina Dettagli Singolo Docente & Motivo Eventuali Mancati Desiderata", expanded=False):
                rep_keys = list(t_reports.keys())
                if rep_keys:
                    sel_rep_tid = st.selectbox(
                        "Seleziona il docente per il dettaglio:",
                        rep_keys,
                        format_func=lambda x: f"{t_reports[x]['name']} ({t_reports[x]['score_percent']}%)",
                        key="tab5_sel_rep_doc_detail"
                    )
                    rep = t_reports[sel_rep_tid]
                    st.markdown(f"#### 👤 {rep['name']} — {rep['status_badge']}")
                    cd1, cd2, cd3, cd4 = st.columns(4)
                    with cd1:
                        st.markdown(f"**Giorno Libero**: {rep['free_day_status']}")
                        st.caption(f"Richiesti: {', '.join(rep['requested_free_days']) if rep['requested_free_days'] else 'Nessuno'}")
                    with cd2:
                        st.markdown(f"**Ingressi Tardi**: {rep['late_entry_result']}")
                        st.markdown(f"**Uscite Presto**: {rep['early_exit_result']}")
                    with cd3:
                        st.markdown(f"**Ore Buche**: {rep['gap_hours']} ore")
                        st.markdown(f"**Slot Sconsigliati**: {rep['soft_slots_result']}")
                    with cd4:
                        st.markdown(f"**Blocchi 2 Ore**: {rep['double_hours_result']}")
                        st.markdown(f"**Punteggio**: `{rep['score_percent']}%`")

        # -------------------------------------------------------------
        # SEZIONE RITOCCHI MANUALI, SMART REPAIR & UPLOAD EXCEL
        # -------------------------------------------------------------
        # -------------------------------------------------------------
        # SEZIONE GENERATORE SOSTEGNO & POTENZIAMENTO
        # -------------------------------------------------------------
        st.divider()
        render_support_solver_section(problem, st.session_state.get("result", res))

# =============================================================
# TAB 6: VISUALIZZA ORARIO & ESPORTAZIONI
# =============================================================
with tabs[5]:
    st.header("📅 Visualizza Orario & Esportazioni")
    st.caption("Visualizza i prospetti orari completi a video, con tabellone docenti, per classe, per aula DADA e scarica in Excel o PDF.")

    res_tab7: Optional[TimetableResult] = st.session_state.get("result")
    if not res_tab7 or res_tab7.status not in ["OPTIMAL", "FEASIBLE"]:
        st.info("ℹ️ **Nessun orario calcolato al momento**: Vai nella scheda **🚀 6. Genera Orario** per avviare il solutore e produrre l'orario scolastico.")
    else:
        res = res_tab7
        sup_res_obj = st.session_state.get("support_result")
        
        # 1. ESPORTAZIONI EXCEL
        st.markdown("##### 📊 Esportazioni Excel (.xlsx)")
        ex_col1, ex_col2 = st.columns(2)
        with ex_col1:
            tabellone_excel_bytes = generate_excel_tabellone_combo(problem, res, support_result=sup_res_obj)
            st.download_button(
                label="📊 Scarica Tabellone Generale Excel (Combo Curricolare + Sostegno - 1 riga/docente)",
                data=tabellone_excel_bytes,
                file_name=f"Tabellone_Docenti_Combo_{problem.config.school_name.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True
            )
        with ex_col2:
            excel_bytes = generate_excel_timetable(problem, res, support_result=sup_res_obj)
            st.download_button(
                label="📑 Scarica Cartella Excel Completa (Tutti i Fogli: Classi, Docenti, Aule, Sostegno)",
                data=excel_bytes,
                file_name=f"Orario_Completo_{problem.config.school_name.replace(' ', '_')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # 2. ESPORTAZIONI PDF
        st.write("")
        st.markdown("##### 📄 Esportazioni PDF Alta Definizione (A4 Orizzontale - 1 griglia per pagina)")
        pdf_c1, pdf_c2, pdf_c3 = st.columns(3)
        with pdf_c1:
            if st.button("📄 Genera PDF Classi", use_container_width=True, key="btn_prep_pdf_classes"):
                with st.spinner("Rendering PDF Classi (1 per foglio)..."):
                    st.session_state.pdf_classes_bytes = generate_classes_pdf(problem, res)
            if "pdf_classes_bytes" in st.session_state and st.session_state.pdf_classes_bytes:
                st.download_button(
                    label="⬇️ Scarica PDF Classi (.pdf)",
                    data=st.session_state.pdf_classes_bytes,
                    file_name=f"Orario_Classi_{problem.config.school_name.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        with pdf_c2:
            if st.button("📄 Genera PDF Docenti Curricolari", use_container_width=True, key="btn_prep_pdf_teachers"):
                with st.spinner("Rendering PDF Docenti (1 per foglio)..."):
                    st.session_state.pdf_teachers_bytes = generate_teachers_pdf(problem, res)
            if "pdf_teachers_bytes" in st.session_state and st.session_state.pdf_teachers_bytes:
                st.download_button(
                    label="⬇️ Scarica PDF Docenti (.pdf)",
                    data=st.session_state.pdf_teachers_bytes,
                    file_name=f"Orario_Docenti_{problem.config.school_name.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        with pdf_c3:
            if problem.rooms:
                if st.button("📄 Genera PDF Aule / DADA", use_container_width=True, key="btn_prep_pdf_rooms"):
                    with st.spinner("Rendering PDF Aule (1 per foglio)..."):
                        st.session_state.pdf_rooms_bytes = generate_rooms_pdf(problem, res)
                if "pdf_rooms_bytes" in st.session_state and st.session_state.pdf_rooms_bytes:
                    st.download_button(
                        label="⬇️ Scarica PDF Aule (.pdf)",
                        data=st.session_state.pdf_rooms_bytes,
                        file_name=f"Orario_Aule_{problem.config.school_name.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            else:
                st.info("Nessuna aula DADA configurata.")
                
        # 3. Seconda riga export dedicata al Sostegno & Inclusione
        if sup_res_obj and sup_res_obj.status in ["OPTIMAL", "FEASIBLE"]:
            st.write("")
            st.markdown("##### ♿ Esportazioni PDF Sostegno & Inclusione Integrata")
            sdown_c1, sdown_c2 = st.columns(2)
            with sdown_c1:
                if st.button("♿ Genera PDF Docenti di Sostegno (1 per foglio)", use_container_width=True, key="btn_prep_pdf_sup_t"):
                    with st.spinner("Rendering PDF Docenti Sostegno..."):
                        st.session_state.pdf_sup_teachers_bytes = generate_support_teachers_pdf(problem, res, sup_res_obj)
                if "pdf_sup_teachers_bytes" in st.session_state and st.session_state.pdf_sup_teachers_bytes:
                    st.download_button(
                        label="⬇️ Scarica PDF Docenti Sostegno (.pdf)",
                        data=st.session_state.pdf_sup_teachers_bytes,
                        file_name=f"Orario_Docenti_Sostegno_{problem.config.school_name.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
            with sdown_c2:
                if st.button("🏫 Genera PDF Classi con Sostegni & Compresenze (1 per foglio)", use_container_width=True, key="btn_prep_pdf_cls_sup"):
                    with st.spinner("Rendering PDF Classi con Sostegni..."):
                        st.session_state.pdf_cls_sup_bytes = generate_classes_with_support_pdf(problem, res, sup_res_obj)
                if "pdf_cls_sup_bytes" in st.session_state and st.session_state.pdf_cls_sup_bytes:
                    st.download_button(
                        label="⬇️ Scarica PDF Classi con Sostegni (.pdf)",
                        data=st.session_state.pdf_cls_sup_bytes,
                        file_name=f"Orario_Classi_con_Sostegni_{problem.config.school_name.replace(' ', '_')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
        
        st.divider()
        
        view_options = ["📊 Tabellone Generale Docenti", "Per Docente (Singolo)", "Per Classe"]
        if problem.rooms:
            view_options.append("Per Aula / DADA")
        view_options.append("🤝 Sostegno, DVA & Potenziamento")
            
        view_mode = st.radio("Modalità di Visualizzazione:", view_options, horizontal=True)
        
        days_active = problem.config.active_days
        
        # Calcola le ore massime effettive per ciascun giorno (inclusi i pomeriggi di rientro fino a 8ª/9ª ora)
        daily_hours = list(problem.config.daily_hours[:problem.config.num_days])
        for d in range(len(daily_hours)):
            for g_map in [res.grid_by_class, res.grid_by_teacher]:
                for entity_id, g in g_map.items():
                    if d < len(g):
                        daily_hours[d] = max(daily_hours[d], len(g[d]))
                        
        max_h = max(daily_hours) if daily_hours else 6

        if view_mode == "📊 Tabellone Generale Docenti":
            st.subheader("📊 Tabellone Generale Docenti (1 Riga per Docente)")
            st.caption("Visualizzazione orizzontale compatta: ogni riga rappresenta un docente con classe, disciplina, eventuale aula e compresenze / sostegno.")
            
            inc_sup_tab = st.checkbox("👥 Includi Docenti di Sostegno / Potenziamento nel Tabellone Generale", value=True, key="chk_inc_sup_tabellone")
            
            tabellone_rows = []
            for t_id, teacher in problem.teachers.items():
                t_assignments = [a for a in problem.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
                tot_cur_h = sum(a.hours_per_week for a in t_assignments)
                
                t_sup_assigns = [sa for sa in problem.support_assignments if sa.teacher_id == t_id]
                t_pot_assigns = [ea for ea in problem.enhancement_assignments if ea.teacher_id == t_id]
                tot_sup_h = sum(sa.hours_per_week for sa in t_sup_assigns) + sum(ea.hours_per_week for ea in t_pot_assigns)
                
                is_sup_t = tot_sup_h > 0 or "sostegno" in teacher.name.lower()
                
                if tot_cur_h == 0 and not (inc_sup_tab and is_sup_t and tot_sup_h > 0):
                    continue
                    
                tot_h = tot_cur_h + (tot_sup_h if inc_sup_tab else 0)
                is_pt = getattr(teacher, "is_part_time", False) or tot_h < 15
                max_w = getattr(teacher, "max_working_days", None)
                
                if is_sup_t:
                    contratto_txt = f"Sostegno PT ({tot_h}h)" if is_pt else "Sostegno (18h)"
                else:
                    contratto_txt = f"PT (max {max_w} gg)" if (is_pt and max_w) else ("Part-Time" if is_pt else "Tempo Pieno")
                
                row_dict = {
                    "Docente": teacher.name,
                    "Contratto / Ruolo": contratto_txt,
                    "Tot Ore": tot_h
                }

                if not is_sup_t:
                    day_has_lessons = [False] * problem.config.num_days
                    for d_idx in range(problem.config.num_days):
                        for h in range(daily_hours[d_idx]):
                            if t_id in res.grid_by_teacher and res.grid_by_teacher[t_id][d_idx][h] is not None:
                                day_has_lessons[d_idx] = True
                                break

                    for d_idx, day_name in enumerate(days_active):
                        is_day_free = not day_has_lessons[d_idx]
                        lessons_in_day = [res.grid_by_teacher[t_id][d_idx][hh] is not None for hh in range(daily_hours[d_idx])] if (t_id in res.grid_by_teacher and not is_day_free) else []
                        first_l = next((idx for idx, val in enumerate(lessons_in_day) if val), None) if lessons_in_day else None
                        last_l = next((idx for idx in reversed(range(len(lessons_in_day))) if lessons_in_day[idx]), None) if lessons_in_day else None

                        for h in range(daily_hours[d_idx]):
                            col_key = f"{day_name[:3]} {h+1}ª"
                            if is_day_free:
                                row_dict[col_key] = "🟢 LIB"
                            else:
                                slot_info = res.grid_by_teacher.get(t_id, [])[d_idx][h] if t_id in res.grid_by_teacher else None
                                if slot_info:
                                    clean_c = slot_info.class_name.replace("ª", "").replace(" ", "") if slot_info.class_name else ""
                                    clean_s = slot_info.subject_name.split("(")[0].strip()[:4] if slot_info.subject_name else ""
                                    clean_r = slot_info.room_name.split("(")[0].strip().replace("ª", "").replace("  ", " ") if getattr(slot_info, "room_name", None) else ""
                                    room_tag = f" [{clean_r}]" if clean_r else ""
                                    c_flag = " 👥" if (getattr(slot_info, "is_compresenza", False) or getattr(slot_info, "compresenza_text", "")) else ""
                                    row_dict[col_key] = f"{clean_c} ({clean_s}){room_tag}{c_flag}"
                                else:
                                    if first_l is not None and last_l is not None and first_l < h < last_l:
                                        row_dict[col_key] = "🟠 BUCA"
                                    else:
                                        row_dict[col_key] = "-"
                else:
                    # Riferimento alla griglia di sostegno
                    sup_g = sup_res_obj.grid_by_support_teacher.get(t_id, []) if sup_res_obj else []
                    day_has_lessons = [False] * problem.config.num_days
                    for d_idx in range(problem.config.num_days):
                        for h in range(daily_hours[d_idx]):
                            if d_idx < len(sup_g) and h < len(sup_g[d_idx]) and sup_g[d_idx][h]:
                                day_has_lessons[d_idx] = True
                                break

                    for d_idx, day_name in enumerate(days_active):
                        is_day_free = not day_has_lessons[d_idx]
                        lessons_in_day = [bool(sup_g[d_idx][hh]) for hh in range(daily_hours[d_idx])] if (d_idx < len(sup_g) and not is_day_free) else []
                        first_l = next((idx for idx, val in enumerate(lessons_in_day) if val), None) if lessons_in_day else None
                        last_l = next((idx for idx in reversed(range(len(lessons_in_day))) if lessons_in_day[idx]), None) if lessons_in_day else None

                        for h in range(daily_hours[d_idx]):
                            col_key = f"{day_name[:3]} {h+1}ª"
                            if is_day_free:
                                row_dict[col_key] = "🟢 LIB"
                            else:
                                slots = sup_g[d_idx][h] if (d_idx < len(sup_g) and h < len(sup_g[d_idx])) else []
                                if slots:
                                    sl = slots[0]
                                    clean_c = sl.class_name.replace("ª", "").replace(" ", "") if sl.class_name else ""
                                    clean_stud = sl.student_name.replace("Alunno ", "")[:8] if sl.student_name else (sl.activity_type.upper() if sl.is_enhancement else "Sost.")
                                    cur_s = sl.curricular_subject_name[:4] if sl.curricular_subject_name else ""
                                    clean_r = sl.room_name.split("(")[0].strip().replace("ª", "").replace("  ", " ") if getattr(sl, "room_name", None) else ""
                                    room_tag = f" [{clean_r}]" if clean_r else ""
                                    row_dict[col_key] = f"♿ {clean_c} ({clean_stud}){room_tag} [{cur_s}]"
                                else:
                                    if first_l is not None and last_l is not None and first_l < h < last_l:
                                        row_dict[col_key] = "🟠 BUCA"
                                    else:
                                        row_dict[col_key] = "-"

                tabellone_rows.append(row_dict)

            st.dataframe(pd.DataFrame(tabellone_rows), use_container_width=True, hide_index=True)

        elif view_mode == "Per Classe":
            sel_c = st.selectbox("Seleziona Classe:", list(problem.classes.keys()), format_func=lambda x: problem.classes[x].name.replace("ª", "").replace(" ", ""))
            
            if sel_c and sel_c in res.grid_by_class:
                clean_sel_c = problem.classes[sel_c].name.replace("ª", "").replace(" ", "")
                st.subheader(f"📅 Orario Settimanale - Classe {clean_sel_c}")
                
                # Calcola le ore giornaliere effettive per questa specifica classe (es. 8h nei giorni di rientro pomeridiano)
                c_grid = res.grid_by_class[sel_c]
                class_dh = [len(c_grid[d]) if d < len(c_grid) else daily_hours[d] for d in range(len(days_active))]
                
                grid_html = render_html_schedule_table(days_active, class_dh, c_grid, view_type="class")
                if hasattr(st, "html"):
                    st.html(grid_html)
                else:
                    st.markdown(grid_html, unsafe_allow_html=True)

        elif view_mode == "Per Docente (Singolo)":
            curricular_teachers = [t_id for t_id in problem.teachers.keys() if any(a.teacher_id == t_id or t_id in a.co_teacher_ids for a in problem.assignments)]
            sel_t = st.selectbox("Seleziona Docente Curricolare:", curricular_teachers, format_func=lambda x: problem.teachers[x].name)
            
            if sel_t and sel_t in res.grid_by_teacher:
                teacher = problem.teachers[sel_t]
                st.subheader(f"📅 Orario Settimanale - {teacher.name}")
                if teacher.free_day_1:
                    st.caption(f"Giorno libero richiesto: **{teacher.free_day_1}** (2ª scelta: {teacher.free_day_2 or 'Nessuna'})")

                t_grid = res.grid_by_teacher[sel_t]
                t_dh = [len(t_grid[d]) if d < len(t_grid) else daily_hours[d] for d in range(len(days_active))]
                
                day_has_lessons = [False] * problem.config.num_days
                for d_idx in range(problem.config.num_days):
                    for h in range(t_dh[d_idx]):
                        if res.grid_by_teacher[sel_t][d_idx][h] is not None:
                            day_has_lessons[d_idx] = True
                            break

                grid_html = render_html_schedule_table(days_active, t_dh, res.grid_by_teacher[sel_t], view_type="teacher", day_has_lessons=day_has_lessons)
                if hasattr(st, "html"):
                    st.html(grid_html)
                else:
                    st.markdown(grid_html, unsafe_allow_html=True)

        elif view_mode == "Per Aula / DADA":
            sel_r = st.selectbox("Seleziona Aula / Ambiente:", list(problem.rooms.keys()), format_func=lambda x: problem.rooms[x].name)
            
            if sel_r and sel_r in res.grid_by_room:
                room = problem.rooms[sel_r]
                st.subheader(f"📅 Occupazione Settimanale - {room.name}")
                if room.subject_ids:
                    s_names = [problem.subjects[s].name for s in room.subject_ids if s in problem.subjects]
                    st.caption(f"Discipline ospitate: **{', '.join(s_names)}**")

                grid_html = render_html_schedule_table(days_active, daily_hours, res.grid_by_room[sel_r], view_type="room")
                if hasattr(st, "html"):
                    st.html(grid_html)
                else:
                    st.markdown(grid_html, unsafe_allow_html=True)

        elif view_mode == "🤝 Sostegno, DVA & Potenziamento":
            render_support_timetables_view(problem, res, st.session_state.get("support_result"))
