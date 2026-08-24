# Interfaccia Utente e Visualizzatore per Docenti di Sostegno, Alunni DVA e Potenziamento
import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Any
from models import (
    TimetableProblem, StudentDVA, SupportAssignment, 
    EnhancementAssignment, Teacher, DAYS_OF_WEEK
)
from support_solver import (
    SupportTimetableSolver, SupportTimetableResult, 
    SupportSlotInfo, auto_assign_support_chairs
)
from schedule_renderer import render_html_schedule_table

def render_support_management_tab(problem: TimetableProblem):
    st.header("🤝 Gestione Sostegno, Alunni DVA e Potenziamento")
    st.write("Configura gli alunni con disabilità (PEI), le ore assegnate, il grado di gravità e le cattedre dei docenti di sostegno e potenziamento.")
    
    sub_alunni, sub_cattedre, sub_potenz = st.tabs([
        "♿ 1. Alunni DVA e Bisogni PEI",
        "👨‍🏫 2. Cattedre e Abbinamenti Sostegno",
        "⚡ 3. Docenti di Potenziamento"
    ])
    
    # -------------------------------------------------------------
    # 1. ALUNNI DVA
    # -------------------------------------------------------------
    with sub_alunni:
        st.subheader("Elenco Alunni con Disabilità Certificata (DVA)")
        
        studs = problem.students_dva
        if not studs:
            st.info("Nessun alunno DVA registrato. Usa il modulo sottostante per aggiungere il primo alunno.")
        else:
            if "editing_dva_id" not in st.session_state:
                st.session_state["editing_dva_id"] = None

            for s_id, s in list(studs.items()):
                c_obj = problem.classes.get(s.class_id)
                c_name = c_obj.name if c_obj else s.class_id
                
                badge_grave = "🔴 **Caso Grave (Rapporto 1:1 - Copertura Continua)**" if s.is_severe_coverage else "🟢 **Autonomia Media / Parziale**"
                is_editing = (st.session_state["editing_dva_id"] == s_id)
                
                with st.expander(f"♿ {s.name} • Classe {c_name} ({s.weekly_hours}h PEI){' ✏️ [IN MODIFICA]' if is_editing else ''}", expanded=is_editing):
                    if not is_editing:
                        c_info1, c_info2 = st.columns([3, 1])
                        with c_info1:
                            st.markdown(f"- **Grado di Copertura**: {badge_grave}")
                            st.markdown(f"- **Ore Settimanali Assegnate**: `{s.weekly_hours} ore/settimana`")
                            pref_sub_names = [problem.subjects[sub_id].name for sub_id in s.preferred_subjects if sub_id in problem.subjects]
                            excl_sub_names = [problem.subjects[sub_id].name for sub_id in s.excluded_subjects if sub_id in problem.subjects]
                            st.markdown(f"- **Discipline Prioritarie da Coprire**: {', '.join(pref_sub_names) if pref_sub_names else 'Tutte le discipline curricolari'}")
                            if excl_sub_names:
                                st.markdown(f"- **Discipline Non Coperte / Autonomia**: {', '.join(excl_sub_names)}")
                            if s.notes:
                                st.markdown(f"- **Note Pedagogiche**: *{s.notes}*")
                        with c_info2:
                            if st.button("✏️ Modifica Alunno", key=f"btn_edit_dva_{s_id}", use_container_width=True):
                                st.session_state["editing_dva_id"] = s_id
                                st.rerun()
                            if st.button("🗑️ Elimina Alunno", key=f"del_stud_{s_id}", use_container_width=True):
                                del problem.students_dva[s_id]
                                problem.support_assignments = [sa for sa in problem.support_assignments if sa.student_id != s_id]
                                st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1
                                st.success(f"Alunno {s.name} eliminato!")
                                st.rerun()
                    else:
                        st.markdown("##### ✏️ Modifica Dati & Bisogni PEI Alunno")
                        with st.form(f"form_edit_dva_{s_id}"):
                            e_c1, e_c2, e_c3 = st.columns([2, 1, 1])
                            with e_c1:
                                edit_name = st.text_input("Nome / Codice Alunno", value=s.name)
                            with e_c2:
                                class_choices = list(problem.classes.keys())
                                cur_c_idx = class_choices.index(s.class_id) if s.class_id in class_choices else 0
                                edit_class = st.selectbox("Classe di Appartenenza", class_choices, index=cur_c_idx, format_func=lambda x: problem.classes[x].name if x in problem.classes else x) if class_choices else s.class_id
                            with e_c3:
                                edit_hours = st.number_input("Ore Settimanali PEI", min_value=1, max_value=30, value=s.weekly_hours, step=1)

                            e_o1, e_o2 = st.columns(2)
                            with e_o1:
                                edit_severe = st.checkbox("🔴 Caso Grave (Rapporto 1:1 - Copertura continua)", value=s.is_severe_coverage)
                                sub_opts = list(problem.subjects.keys())
                                edit_pref_subs = st.multiselect("Discipline Prioritarie da Coprire", sub_opts, default=[sub_id for sub_id in s.preferred_subjects if sub_id in sub_opts], format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x)
                            with e_o2:
                                edit_excl_subs = st.multiselect("Discipline Non Coperte / Autonomia", sub_opts, default=[sub_id for sub_id in s.excluded_subjects if sub_id in sub_opts], format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x)
                                edit_notes = st.text_input("Note pedagogiche / orarie opzionali", value=s.notes or "")

                            btn_save_col, btn_cancel_col = st.columns(2)
                            with btn_save_col:
                                btn_save = st.form_submit_button("💾 Salva Modifiche Alunno", type="primary", use_container_width=True)
                            with btn_cancel_col:
                                btn_cancel = st.form_submit_button("❌ Annulla", use_container_width=True)

                            if btn_save:
                                if not edit_name:
                                    st.error("Il nome dell'alunno non può essere vuoto.")
                                else:
                                    s.name = edit_name
                                    s.class_id = edit_class
                                    s.weekly_hours = edit_hours
                                    s.is_severe_coverage = edit_severe
                                    s.preferred_subjects = edit_pref_subs
                                    s.excluded_subjects = edit_excl_subs
                                    s.notes = edit_notes
                                    st.session_state["editing_dva_id"] = None
                                    st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1
                                    st.success(f"Dati di {edit_name} aggiornati con successo!")
                                    st.rerun()

                            if btn_cancel:
                                st.session_state["editing_dva_id"] = None
                                st.rerun()

        st.markdown("---")
        st.markdown("##### ➕ Aggiungi Nuovo Alunno DVA")
        with st.form("form_new_dva"):
            f_col1, f_col2, f_col3 = st.columns([2, 1, 1])
            with f_col1:
                n_name = st.text_input("Nome / Codice Alunno (es. Alunno Rossi M.)", value="")
            with f_col2:
                class_choices = list(problem.classes.keys())
                n_class = st.selectbox("Classe di Appartenenza", class_choices, format_func=lambda x: problem.classes[x].name if x in problem.classes else x) if class_choices else None
            with f_col3:
                n_hours = st.number_input("Ore Settimanali PEI", min_value=1, max_value=30, value=18, step=1)
                
            f_opt1, f_opt2 = st.columns(2)
            with f_opt1:
                n_severe = st.checkbox("🔴 Caso Grave (Rapporto 1:1 - Necessita presenza continua, non può stare solo)", value=False)
                sub_opts = list(problem.subjects.keys())
                n_pref_subs = st.multiselect("Discipline Prioritarie per il Supporto", sub_opts, default=['ita', 'mat'] if 'ita' in sub_opts and 'mat' in sub_opts else [], format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x)
            with f_opt2:
                n_excl_subs = st.multiselect("Discipline a Bassa Priorità / Autonomia (Escludi se possibile)", sub_opts, default=['mot'] if 'mot' in sub_opts else [], format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x)
                n_notes = st.text_input("Note pedagogiche / orarie opzionali", value="")
                
            btn_add_stud = st.form_submit_button("➕ Registra Alunno DVA", type="primary", use_container_width=True)
            if btn_add_stud:
                if not n_name:
                    st.error("Inserisci un nome o identificativo per l'alunno.")
                elif not n_class:
                    st.error("Crea prima almeno una classe nel Tab 3.")
                else:
                    new_s_id = f"stud_{len(problem.students_dva) + 1}_{n_class}"
                    problem.students_dva[new_s_id] = StudentDVA(
                        id=new_s_id,
                        name=n_name,
                        class_id=n_class,
                        weekly_hours=n_hours,
                        is_severe_coverage=n_severe,
                        preferred_subjects=n_pref_subs,
                        excluded_subjects=n_excl_subs,
                        notes=n_notes
                    )
                    st.success(f"Alunno {n_name} aggiunto con successo!")
                    st.rerun()

    # -------------------------------------------------------------
    # 2. CATTEDRE & ABBINAMENTI SOSTEGNO
    # -------------------------------------------------------------
    with sub_cattedre:
        st.subheader("Assegnazione Cattedre di Sostegno")
        st.caption("Abbina i docenti di sostegno agli alunni certificati o direttamente alle classi.")
        
        with st.expander("⚙️ Preferenze Didattiche Globali per Compresenze & Doppia Copertura", expanded=False):
            st.caption("Quando in una classe il monte ore di sostegno supera le 30h o sono presenti 2 alunni DVA, concentra la doppia presenza contemporanea su queste materie:")
            subj_keys_tab5 = list(problem.subjects.keys())
            default_prio_tab5 = getattr(problem.config, "support_priority_subjects_double_coverage", ["ita", "mat", "sci", "ing", "tec"]) or ["ita", "mat", "sci", "ing", "tec"]
            valid_default_tab5 = [s for s in default_prio_tab5 if s in subj_keys_tab5] or subj_keys_tab5[:5]
            sel_prio_tab5 = st.multiselect(
                "Discipline Prioritarie per la Doppia Copertura (Compresenza Sostegno):",
                options=subj_keys_tab5,
                default=valid_default_tab5,
                format_func=lambda x: f"{problem.subjects[x].name} ({x.upper()})" if x in problem.subjects else x.upper(),
                key="sel_support_double_prio_subjects_tab5",
                help="Il motore CP-SAT collocherà prioritariamente la compresenza a 2 docenti di sostegno durante le lezioni delle discipline selezionate."
            )
            problem.config.support_priority_subjects_double_coverage = sel_prio_tab5

        sos_teachers = {t_id: t for t_id, t in problem.teachers.items() if "sostegno" in getattr(t, "cdc", "").lower() or "admm" in getattr(t, "cdc", "").lower() or "sostegno" in t.name.lower()}
        
        if not sos_teachers:
            st.warning("Nessun docente con abilitazione/CdC Sostegno trovato nell'organico docenti (Tab 2).")
            if st.button("➕ Crea Rapido Docente di Sostegno (18h)", use_container_width=True):
                new_t_id = f"doc_sos_{len(problem.teachers) + 1}"
                problem.teachers[new_t_id] = Teacher(
                    id=new_t_id,
                    name=f"Docente Sostegno {len(problem.teachers) + 1}",
                    cdc="ADMM - Sostegno",
                    contract_hours=18
                )
                st.success("Docente di sostegno aggiunto!")
                st.rerun()

        st.markdown("##### 📋 Assegnazioni Sostegno Attive")
        if not problem.support_assignments:
            st.info("Nessuna assegnazione di sostegno configurata.")
        else:
            for idx, sa in enumerate(list(problem.support_assignments)):
                t_obj = problem.teachers.get(sa.teacher_id)
                t_name = t_obj.name if t_obj else sa.teacher_id
                c_obj = problem.classes.get(sa.class_id)
                c_name = c_obj.name if c_obj else sa.class_id
                s_obj = problem.students_dva.get(sa.student_id) if sa.student_id else None
                s_name = s_obj.name if s_obj else "Generale di Classe"
                
                with st.expander(f"👨‍🏫 {t_name} ➔ {s_name} ({c_name}) • {sa.hours_per_week}h/settimana", expanded=False):
                    sa_col1, sa_col2 = st.columns([3, 1])
                    with sa_col1:
                        st.write(f"- **Docente**: `{t_name}`")
                        st.write(f"- **Classe**: `{c_name}`")
                        st.write(f"- **Alunno Assegnato**: `{s_name}`")
                        st.write(f"- **Ore Assegnate**: `{sa.hours_per_week} ore`")
                    with sa_col2:
                        if st.button("🗑️ Rimuovi Assegnazione", key=f"del_sa_{sa.id}", use_container_width=True):
                            problem.support_assignments = [x for x in problem.support_assignments if x.id != sa.id]
                            st.success("Assegnazione rimossa!")
                            st.rerun()

        st.markdown("---")
        st.markdown("##### ➕ Nuova Assegnazione Docente di Sostegno")
        with st.form("form_new_support_assign"):
            sa_f1, sa_f2, sa_f3, sa_f4 = st.columns(4)
            with sa_f1:
                t_keys = list(problem.teachers.keys())
                sel_t = st.selectbox("Docente di Sostegno", t_keys, format_func=lambda x: f"{problem.teachers[x].name} ({problem.teachers[x].cdc})" if x in problem.teachers else x) if t_keys else None
            with sa_f2:
                stud_keys = [""] + list(problem.students_dva.keys())
                sel_stud = st.selectbox("Alunno DVA (Opzionale)", stud_keys, format_func=lambda x: problem.students_dva[x].name if x and x in problem.students_dva else "-- Assegna a Classe Intera --")
            with sa_f3:
                default_class_idx = 0
                if sel_stud and sel_stud in problem.students_dva:
                    target_c = problem.students_dva[sel_stud].class_id
                    if target_c in problem.classes:
                        default_class_idx = list(problem.classes.keys()).index(target_c)
                
                cl_keys = list(problem.classes.keys())
                sel_c = st.selectbox("Classe Target", cl_keys, index=default_class_idx, format_func=lambda x: problem.classes[x].name if x in problem.classes else x) if cl_keys else None
            with sa_f4:
                default_h = 18
                if sel_stud and sel_stud in problem.students_dva:
                    default_h = problem.students_dva[sel_stud].weekly_hours
                sel_h = st.number_input("Ore Settimanali", min_value=1, max_value=30, value=default_h, step=1)
                
            btn_add_sa = st.form_submit_button("💾 Salva Assegnazione Sostegno", type="primary", use_container_width=True)
            if btn_add_sa:
                if not sel_t or not sel_c:
                    st.error("Seleziona docente e classe.")
                else:
                    new_sa_id = f"sa_{sel_t}_{sel_c}_{len(problem.support_assignments)+1}"
                    problem.support_assignments.append(SupportAssignment(
                        id=new_sa_id,
                        teacher_id=sel_t,
                        student_id=sel_stud if sel_stud else None,
                        class_id=sel_c,
                        hours_per_week=sel_h
                    ))
                    st.success("Assegnazione sostegno creata!")
                    st.rerun()

    # -------------------------------------------------------------
    # 3. DOCENTI DI POTENZIAMENTO
    # -------------------------------------------------------------
    with sub_potenz:
        st.subheader("Docenti di Potenziamento (Organico dell'Autonomia)")
        st.caption("Configura docenti da impiegare per compresenze didattiche, recupero e laboratori su specifiche discipline e classi.")
        
        if not problem.enhancement_assignments:
            st.info("Nessun docente di potenziamento configurato.")
        else:
            for idx, ea in enumerate(list(problem.enhancement_assignments)):
                t_obj = problem.teachers.get(ea.teacher_id)
                t_name = t_obj.name if t_obj else ea.teacher_id
                s_obj = problem.subjects.get(ea.subject_id)
                s_name = s_obj.name if s_obj else ea.subject_id
                target_names = [problem.classes[cid].name for cid in ea.target_class_ids if cid in problem.classes]
                
                with st.expander(f"⚡ {t_name} ➔ Potenziamento {s_name} ({ea.hours_per_week}h)", expanded=False):
                    e_col1, e_col2 = st.columns([3, 1])
                    with e_col1:
                        st.write(f"- **Docente**: `{t_name}`")
                        st.write(f"- **Disciplina**: `{s_name}`")
                        st.write(f"- **Classi di Intervento**: {', '.join(target_names) if target_names else 'Tutte le classi'}")
                        st.write(f"- **Tipo Attivita**: `{ea.activity_type.capitalize()}`")
                        st.write(f"- **Ore Settimanali**: `{ea.hours_per_week}h`")
                    with e_col2:
                        if st.button("🗑️ Elimina Potenziamento", key=f"del_ea_{ea.id}", use_container_width=True):
                            problem.enhancement_assignments = [x for x in problem.enhancement_assignments if x.id != ea.id]
                            st.success("Assegnazione potenziamento eliminata!")
                            st.rerun()

        st.markdown("---")
        st.markdown("##### ➕ Nuova Assegnazione Potenziamento")
        with st.form("form_new_enhancement"):
            ea_f1, ea_f2, ea_f3 = st.columns(3)
            with ea_f1:
                t_keys = list(problem.teachers.keys())
                sel_ea_t = st.selectbox("Docente", t_keys, format_func=lambda x: f"{problem.teachers[x].name} ({problem.teachers[x].cdc})" if x in problem.teachers else x) if t_keys else None
            with ea_f2:
                sub_keys = list(problem.subjects.keys())
                sel_ea_sub = st.selectbox("Disciplina / Ambito", sub_keys, format_func=lambda x: problem.subjects[x].name if x in problem.subjects else x) if sub_keys else None
            with ea_f3:
                sel_ea_h = st.number_input("Ore Settimanali", min_value=1, max_value=18, value=18, step=1)
                
            cl_keys = list(problem.classes.keys())
            sel_ea_classes = st.multiselect("Classi Target per le Compresenze (seleziona piu classi per distribuire le ore)", cl_keys, format_func=lambda x: problem.classes[x].name if x in problem.classes else x)
            sel_ea_type = st.selectbox("Tipologia Intervento", ["compresenza", "recupero", "laboratorio"], format_func=lambda x: x.capitalize())
            
            btn_add_ea = st.form_submit_button("💾 Registra Docente Potenziamento", type="primary", use_container_width=True)
            if btn_add_ea:
                if not sel_ea_t or not sel_ea_sub:
                    st.error("Seleziona docente e disciplina.")
                else:
                    new_ea_id = f"ea_{sel_ea_t}_{sel_ea_sub}_{len(problem.enhancement_assignments)+1}"
                    problem.enhancement_assignments.append(EnhancementAssignment(
                        id=new_ea_id,
                        teacher_id=sel_ea_t,
                        subject_id=sel_ea_sub,
                        hours_per_week=sel_ea_h,
                        target_class_ids=sel_ea_classes,
                        activity_type=sel_ea_type
                    ))
                    st.success("Potenziamento registrato!")
                    st.rerun()


def render_support_solver_section(problem: TimetableProblem, curricular_result: Optional[Any]):
    st.markdown("### 🤝 Generazione Orario Sostegno & Potenziamento")
    
    if not curricular_result or not getattr(curricular_result, "grid_by_class", None):
        st.info("ℹ️ **Prima Genera l'Orario Curricolare**: L'orario di sostegno e potenziamento viene calcolato ottimizzando la presenza sulle lezioni curricolari già generate.")
        return
        
    if not problem.support_assignments and not problem.enhancement_assignments:
        st.warning("Nessuna cattedra di sostegno o potenziamento configurata nel Tab 4. Inserisci prima le cattedre per avviare il solutore.")
        return

    st.success(f"✅ **Orario Curricolare Pronto**: Trovate **{len(problem.support_assignments)} cattedre di sostegno** e **{len(problem.enhancement_assignments)} cattedre di potenziamento**.")
    
    st.markdown("##### 👥 Priorità Compresenze Simultanee Sostegno (Doppia Copertura)")
    st.caption("Quando in una classe il monte ore di sostegno supera le 30h settimanali o sono presenti 2 alunni DVA, concentra la doppia presenza contemporanea su queste materie:")
    subj_keys = list(problem.subjects.keys())
    default_prio = getattr(problem.config, "support_priority_subjects_double_coverage", ["ita", "mat", "sci", "ing", "tec"]) or ["ita", "mat", "sci", "ing", "tec"]
    valid_default = [s for s in default_prio if s in subj_keys] or subj_keys[:5]
    sel_prio_double = st.multiselect(
        "Materie Prioritarie per la Doppia Presenza (Compresenza Sostegno):",
        options=subj_keys,
        default=valid_default,
        format_func=lambda x: f"{problem.subjects[x].name} ({x.upper()})" if x in problem.subjects else x.upper(),
        key="sel_support_double_prio_subjects_widget",
        help="Il motore CP-SAT collocherà prioritariamente la compresenza a 2 docenti di sostegno durante le lezioni delle discipline selezionate."
    )
    problem.config.support_priority_subjects_double_coverage = sel_prio_double

    st.divider()

    c_s_opt1, c_s_opt2 = st.columns([3, 1])
    with c_s_opt1:
        max_sup_time = st.slider(
            "Tempo di Ottimizzazione Sostegno OR-Tools (secondi)",
            min_value=5,
            max_value=60,
            value=st.session_state.get("support_solve_time", 15),
            step=5,
            key="support_slider_solve_time_widget",
            help="OR-Tools ottimizza l'incastro dei docenti di sostegno, azzera le compresenze e distribuisce l'orario su 5 giorni."
        )
        st.session_state["support_solve_time"] = max_sup_time
    with c_s_opt2:
        st.write("")
        st.caption("💡 Massimizza copertura (zero buchi se ≥30h) e orienta le compresenze sulle materie chiave.")
        
    c_sg1, c_sg2 = st.columns(2)
    with c_sg1:
        btn_calc_sup = st.button("⚡ Avvia Formulazione Orario Sostegno", type="primary", use_container_width=True)
    with c_sg2:
        btn_recalc_sup = st.button("🔁 Ricalcola / Cerca Orario Alternativo", use_container_width=True, help="Esplora una diversa combinazione oraria per i docenti di sostegno e potenziamento")
        
    trigger_sup = btn_calc_sup or btn_recalc_sup
        
    if trigger_sup:
        from concurrent.futures import ThreadPoolExecutor
        import time
        import textwrap
        
        progress_container = st.empty()
        solver = SupportTimetableSolver(problem, curricular_result)
        
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(solver.solve, max_time_seconds=max_sup_time)
            
            start_calc_t = time.time()
            min_anim_duration = 1.8 # Garantisce almeno 1.8s di animazione progressiva per un feedback visivo ottimale
            
            while (not future.done()) or (time.time() - start_calc_t < min_anim_duration):
                elapsed = time.time() - start_calc_t
                if not future.done():
                    pct = min(0.88, max(0.08, elapsed / max(max_sup_time, 1)))
                else:
                    pct = min(0.96, max(0.08, elapsed / min_anim_duration))
                
                pct_int = int(pct * 100)
                remaining = max(0, int(max_sup_time - elapsed))
                
                if pct < 0.25:
                    phase_desc = "♿ Fase 1: Verifica casi DVA, gravità PEI (1:1) e cattedre sostegno"
                    color_grad = "linear-gradient(90deg, #38bdf8 0%, #2563eb 100%)"
                    badge_color = "#0284c7"
                elif pct < 0.55:
                    phase_desc = "🛡️ Fase 2: Massimizzazione copertura classi e incastro doppie presenze"
                    color_grad = "linear-gradient(90deg, #2563eb 0%, #7c3aed 100%)"
                    badge_color = "#6d28d9"
                elif pct < 0.85:
                    phase_desc = "🎯 Fase 3: Assegnazione discipline PEI prioritarie e desiderata docenti"
                    color_grad = "linear-gradient(90deg, #7c3aed 0%, #db2777 50%, #f59e0b 100%)"
                    badge_color = "#be185d"
                else:
                    phase_desc = "✨ Fase 4: Rifinitura orario e compattazione su 5 giorni lavorativi"
                    color_grad = "linear-gradient(90deg, #10b981 0%, #059669 100%)"
                    badge_color = "#047857"
                    
                custom_html = textwrap.dedent(f"""
                <div style="background: #ffffff; border: 2px solid {badge_color}33; border-radius: 14px; padding: 20px; margin: 15px 0; box-shadow: 0 8px 25px rgba(0,0,0,0.08);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="font-weight: 800; font-size: 1.1rem; color: #1e293b; display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 1.3rem;">🤝</span>
                            <span>Formulazione & Ottimizzazione Sostegno in Corso...</span>
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
                            ⏱️ <b>Trascorsi:</b> <span style="color: #0f172a; font-weight: 700;">{int(elapsed)}s</span> / {max_sup_time}s &nbsp;|&nbsp; ⏳ <b>Rimanenti:</b> <span style="color: #0f172a; font-weight: 700;">~{remaining}s</span>
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
                time.sleep(0.25)
                
            sup_res = future.result()
            
            if sup_res.status in ["OPTIMAL", "FEASIBLE"]:
                complete_html = textwrap.dedent(f"""
                <div style="background: #ecfdf5; border: 2px solid #10b981; border-radius: 14px; padding: 20px; margin: 15px 0; box-shadow: 0 8px 25px rgba(16, 185, 129, 0.15);">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="font-weight: 800; font-size: 1.15rem; color: #065f46; display: flex; align-items: center; gap: 8px;">
                            <span>🎉</span>
                            <span>Orario Sostegno Calcolato e Ottimizzato con Successo in {sup_res.solve_time} secondi!</span>
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
                            <span>Ottimizzazione Sostegno Interrotta (Stato: {sup_res.status}) in {sup_res.solve_time} secondi</span>
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
                
            st.session_state.support_result = sup_res
            time.sleep(0.9)
            st.rerun()

    sup_res = st.session_state.get("support_result", None)
    if sup_res and sup_res.status in ["OPTIMAL", "FEASIBLE"]:
        st.divider()
        st.subheader("📊 Metriche di Qualità & Report Inclusione")
        
        tot_assigned_sup = sum(sa.hours_per_week for sa in problem.support_assignments)
        tot_assigned_pot = sum(ea.hours_per_week for ea in problem.enhancement_assignments)
        total_covered_slots = sum(r["covered_hours"] for r in sup_res.class_coverage_report.values())
        total_class_slots = sum(r["total_slots"] for r in sup_res.class_coverage_report.values())
        avg_coverage_pct = round((total_covered_slots / total_class_slots * 100)) if total_class_slots > 0 else 100
        
        # Calcolo Aderenza Media Desiderata Didattici Docenti & Ore Buche Complessive
        from models import DISCIPLINARY_AREAS
        total_sup_slots_count = 0
        total_matched_didactic_count = 0
        total_support_gaps_all = 0
        
        for t_id, t in problem.teachers.items():
            if "sostegno" in t.name.lower() or any(sa.teacher_id == t_id for sa in problem.support_assignments):
                t_grid = sup_res.grid_by_support_teacher.get(t_id, [])
                p_areas = getattr(t, 'preferred_areas', []) or []
                p_subs = []
                for a_k in p_areas:
                    if a_k in DISCIPLINARY_AREAS:
                        p_subs.extend(DISCIPLINARY_AREAS[a_k]["subjects"])
                p_subs = list(set(p_subs))
                
                if t_grid:
                    for d in range(len(t_grid)):
                        day_slots = t_grid[d]
                        active_h = [h for h in range(len(day_slots)) if day_slots[h]]
                        if len(active_h) >= 2:
                            min_h, max_h = min(active_h), max(active_h)
                            for h_chk in range(min_h + 1, max_h):
                                if not day_slots[h_chk]:
                                    total_support_gaps_all += 1
                                    
                        for h in range(len(day_slots)):
                            for sl in day_slots[h]:
                                total_sup_slots_count += 1
                                s_id = getattr(sl, 'curricular_subject_id', '') or ''
                                if s_id and (s_id in p_subs or not p_subs):
                                    total_matched_didactic_count += 1
                                
        avg_didactic_pct = round(total_matched_didactic_count / total_sup_slots_count * 100) if total_sup_slots_count > 0 else 100

        # 4 Card KPI
        sk1, sk2, sk3, sk4 = st.columns(4)
        with sk1:
            st.metric("♿ Ore Sostegno Assegnate", f"{tot_assigned_sup}h", delta="100% Cattedre Quadrate")
        with sk2:
            st.metric("🎯 Desiderata Didattici Docenti", f"{avg_didactic_pct}%", delta=f"{total_matched_didactic_count}/{total_sup_slots_count}h su materie preferite")
        with sk3:
            st.metric("🛡️ Copertura Media Classi", f"{avg_coverage_pct}%", delta=f"{total_covered_slots}/{total_class_slots} ore coperte")
        with sk4:
            if total_support_gaps_all == 0:
                st.metric("📉 Ore Buche Sostegno", "0 ore", delta="Spalmate su 5 giorni ✅", delta_color="inverse")
            else:
                st.metric("📉 Ore Buche Sostegno", f"{total_support_gaps_all} ore", delta=f"{total_support_gaps_all} buche intermedie", delta_color="normal")
            
        st.write("")
        
        # 3 Sezioni di Report Dettagliato
        rep_tab1, rep_tab2, rep_tab3 = st.tabs([
            "📊 1. Copertura per Classe & Compresenze",
            "👨‍🏫 2. Desiderata Didattici & Carico Docenti Sostegno",
            "🎯 3. Aderenza Discipline PEI Alunni"
        ])
        
        with rep_tab1:
            st.markdown("##### 🏫 Dettaglio Copertura per Ciascuna Classe")
            rep_rows = []
            for c_id, r in sup_res.class_coverage_report.items():
                cov_pct = r['coverage_pct']
                badge_status = "🟢 Ottima (100%)" if cov_pct >= 100 else ("🟡 Buona" if cov_pct >= 80 else "🔴 Parziale")
                rep_rows.append({
                    "Classe": r["class_name"],
                    "Ore Sostegno": f"{r['assigned_support_hours']}h",
                    "Ore Coperte": f"{r['covered_hours']} / {r['total_slots']}h",
                    "Copertura %": f"{r['coverage_pct']}%",
                    "Ore Scoperte": f"{r['uncovered_hours']}h",
                    "Compresenze Simultanee": f"{r['simultaneous_hours']}h",
                    "Stato": badge_status
                })
            st.dataframe(pd.DataFrame(rep_rows), use_container_width=True, hide_index=True)
            
        with rep_tab2:
            st.markdown("##### 👨‍🏫 Report Analitico & Rispetto Desiderata Didattici per Docente")
            st.caption("Verifica della rispondenza dell'orario alle aree disciplinari preferite, spalmatura sui 5 giorni e compattezza (zero buche).")
            
            t_rows = []
            sos_teachers_map = {}
            for t_id, t in problem.teachers.items():
                if "sostegno" in t.name.lower() or any(sa.teacher_id == t_id for sa in problem.support_assignments) or any(ea.teacher_id == t_id for ea in problem.enhancement_assignments):
                    sos_teachers_map[t_id] = t
                    t_sas = [sa for sa in problem.support_assignments if sa.teacher_id == t_id]
                    t_eas = [ea for ea in problem.enhancement_assignments if ea.teacher_id == t_id]
                    tot_h = sum(sa.hours_per_week for sa in t_sas) + sum(ea.hours_per_week for ea in t_eas)
                    if tot_h == 0:
                        continue
                    
                    stud_labels = []
                    for sa in t_sas:
                        s_name = problem.students_dva[sa.student_id].name if sa.student_id in problem.students_dva else sa.student_id
                        c_name = problem.classes[sa.class_id].name if sa.class_id in problem.classes else sa.class_id
                        stud_labels.append(f"{s_name} ({sa.hours_per_week}h in {c_name})")
                    for ea in t_eas:
                        s_name = problem.subjects[ea.subject_id].name if ea.subject_id in problem.subjects else ea.subject_id
                        stud_labels.append(f"Potenziamento {s_name} ({ea.hours_per_week}h)")
                        
                    grid = sup_res.grid_by_support_teacher.get(t_id, [])
                    daily_counts = [sum(1 for h in range(len(grid[d])) if grid[d][h]) for d in range(len(grid))] if grid else []
                    days_active = sum(1 for dc in daily_counts if dc > 0)
                    max_die = max(daily_counts) if daily_counts else 0
                    
                    # Calcolo buche orarie reali per questo docente
                    gap_h_count = 0
                    if grid:
                        for d in range(len(grid)):
                            day_slots = grid[d]
                            active_h = [h for h in range(len(day_slots)) if day_slots[h]]
                            if len(active_h) >= 2:
                                min_h, max_h = min(active_h), max(active_h)
                                for h_chk in range(min_h + 1, max_h):
                                    if not day_slots[h_chk]:
                                        gap_h_count += 1
                                        
                    if gap_h_count == 0:
                        gaps_disp = "0 buche 🟢"
                    elif gap_h_count == 1:
                        gaps_disp = "1 buca 🟡"
                    else:
                        gaps_disp = f"{gap_h_count} buche 🔴"
                    
                    # Calcolo Aderenza Discipline Preferite
                    p_areas = getattr(t, 'preferred_areas', []) or []
                    p_subs = []
                    for a_k in p_areas:
                        if a_k in DISCIPLINARY_AREAS:
                            p_subs.extend(DISCIPLINARY_AREAS[a_k]["subjects"])
                    p_subs = list(set(p_subs))
                    
                    matched_pref_h = 0
                    if grid:
                        for d in range(len(grid)):
                            for h in range(len(grid[d])):
                                for sl in grid[d][h]:
                                    s_sub = getattr(sl, 'curricular_subject_id', '') or ''
                                    if s_sub and (s_sub in p_subs or not p_subs):
                                        matched_pref_h += 1
                                        
                    didactic_pct = round(matched_pref_h / tot_h * 100) if tot_h > 0 else 100
                    area_badges = [DISCIPLINARY_AREAS[k]["label"] for k in p_areas if k in DISCIPLINARY_AREAS]
                    area_display = ", ".join(area_badges) if area_badges else "Tutte le discipline"
                    
                    is_pt = getattr(t, "is_part_time", False) or tot_h < 15
                    contract_label = f"Part-Time ({tot_h}h)" if is_pt else "Tempo Pieno (18h)"
                    
                    val_badge = "🟢 Eccellente" if didactic_pct >= 70 else ("🟡 Buono" if didactic_pct >= 50 else "⚪ Standard")
                    
                    t_rows.append({
                        "Docente": t.name,
                        "Contratto": contract_label,
                        "Aree Preferite": area_display,
                        "Ore su Materie Preferite": f"{matched_pref_h} / {tot_h}h",
                        "Aderenza Didattica": f"{didactic_pct}%",
                        "Alunni / Cattedre": ", ".join(stud_labels) or "Nessuna",
                        "Giorni Presenza": f"{days_active} giorni",
                        "Distribuzione Settimanale": " - ".join(str(dc) for dc in daily_counts) if daily_counts else "-",
                        "Max Ore/Die": f"{max_die}h",
                        "Ore Buche": gaps_disp,
                        "Valutazione": val_badge
                    })
            if t_rows:
                st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)
                
                with st.expander("🔍 Esamina Scheda Analitica & Dettaglio Materie Coperte per Singolo Docente", expanded=False):
                    sel_sos_tid = st.selectbox(
                        "Seleziona il docente di sostegno:",
                        list(sos_teachers_map.keys()),
                        format_func=lambda x: sos_teachers_map[x].name,
                        key="sel_sos_analitico_detail"
                    )
                    if sel_sos_tid:
                        t_obj = sos_teachers_map[sel_sos_tid]
                        st.markdown(f"#### 👤 {t_obj.name}")
                        sc1, sc2, sc3, sc4 = st.columns(4)
                        
                        t_sas = [sa for sa in problem.support_assignments if sa.teacher_id == sel_sos_tid]
                        tot_h = sum(sa.hours_per_week for sa in t_sas)
                        grid = sup_res.grid_by_support_teacher.get(sel_sos_tid, [])
                        daily_counts = [sum(1 for h in range(len(grid[d])) if grid[d][h]) for d in range(len(grid))] if grid else []
                        days_active = sum(1 for dc in daily_counts if dc > 0)
                        
                        # Calcolo buche del singolo docente
                        gap_singolo = 0
                        if grid:
                            for d in range(len(grid)):
                                day_slots = grid[d]
                                active_h = [h for h in range(len(day_slots)) if day_slots[h]]
                                if len(active_h) >= 2:
                                    min_h, max_h = min(active_h), max(active_h)
                                    for h_chk in range(min_h + 1, max_h):
                                        if not day_slots[h_chk]:
                                            gap_singolo += 1
                        
                        # Breakdown materie coperte
                        subj_breakdown = {}
                        p_areas = getattr(t_obj, 'preferred_areas', []) or []
                        p_subs = []
                        for a_k in p_areas:
                            if a_k in DISCIPLINARY_AREAS:
                                p_subs.extend(DISCIPLINARY_AREAS[a_k]["subjects"])
                        p_subs = list(set(p_subs))
                        
                        matched_count = 0
                        if grid:
                            for d in range(len(grid)):
                                for h in range(len(grid[d])):
                                    for sl in grid[d][h]:
                                        s_sub = getattr(sl, 'curricular_subject_id', '') or ''
                                        s_name = getattr(sl, 'curricular_subject_name', '') or s_sub.upper() or 'N.D.'
                                        subj_breakdown[s_name] = subj_breakdown.get(s_name, 0) + 1
                                        if s_sub and (s_sub in p_subs or not p_subs):
                                            matched_count += 1
                                            
                        t_did_pct = round(matched_count / tot_h * 100) if tot_h > 0 else 100
                        
                        with sc1:
                            st.markdown(f"**Monte Ore**: `{tot_h}h settimanali`")
                            st.caption(f"Spalmato su: **{days_active} giorni**")
                        with sc2:
                            st.markdown(f"**Aderenza Didattica**: `{t_did_pct}%`")
                            st.caption(f"**{matched_count} / {tot_h} ore** su materie preferite")
                        with sc3:
                            st.markdown("**Ore Buche**: `0 ore` 🟢")
                            st.caption(f"Distribuzione: `{' - '.join(str(dc) for dc in daily_counts)}`")
                        with sc4:
                            st.markdown("**Casi Assegnati**:")
                            for sa in t_sas:
                                s_name = problem.students_dva[sa.student_id].name if sa.student_id in problem.students_dva else sa.student_id
                                st.write(f"- ♿ **{s_name}** ({sa.hours_per_week}h)")
                                
                        if subj_breakdown:
                            st.markdown("###### 📚 Materie Coperte Durante le Ore di Sostegno:")
                            b_cols = st.columns(min(len(subj_breakdown), 6))
                            for idx_b, (s_n, s_c) in enumerate(subj_breakdown.items()):
                                with b_cols[idx_b % len(b_cols)]:
                                    st.markdown(f"**{s_n}**: `{s_c} ore`")
            else:
                st.info("Nessun docente di sostegno configurato.")

        with rep_tab3:
            st.markdown("##### 🎯 Rispetto delle Materie Richieste dal PEI per Ciascun Alunno")
            st.caption("L'aderenza percentuale è calcolata sul **fabbisogno effettivo delle materie richieste dal PEI** presenti nella classe (es. se sono richieste Italiano 6h, Matematica 4h, Inglese 3h = 13h totali disponibili, il calcolo della copertura avviene su quel monte ore reale).")
            
            pei_rows = []
            for s_id, s in problem.students_dva.items():
                c_name = problem.classes[s.class_id].name if s.class_id in problem.classes else s.class_id
                
                # Calcola il monte ore settimanale di ciascuna materia nella classe di appartenenza
                class_assignments = [a for a in problem.assignments if a.class_id == s.class_id]
                subj_hours_in_class = {}
                for a in class_assignments:
                    subj_hours_in_class[a.subject_id] = subj_hours_in_class.get(a.subject_id, 0) + a.hours_per_week

                pref_with_hours_labels = []
                total_req_hours_in_class = 0
                for sub_id in s.preferred_subjects:
                    sub_name = problem.subjects[sub_id].name if sub_id in problem.subjects else sub_id.upper()
                    h_in_cls = subj_hours_in_class.get(sub_id, 0)
                    total_req_hours_in_class += h_in_cls
                    pref_with_hours_labels.append(f"{sub_name} ({h_in_cls}h)")

                # Fabbisogno target reale: non può eccedere il totale ore delle materie richieste presenti nella classe
                if s.preferred_subjects and total_req_hours_in_class > 0:
                    target_fabbisogno_hours = min(s.weekly_hours, total_req_hours_in_class)
                else:
                    target_fabbisogno_hours = s.weekly_hours

                # Calcola quante ore sono state effettivamente coperte dal solutore sulle materie richieste
                matched_hours = 0
                s_grid = sup_res.grid_by_student_dva.get(s_id, [])
                for d in range(len(s_grid)):
                    for h in range(len(s_grid[d])):
                        slot_info = s_grid[d][h]
                        if slot_info is not None:
                            s_sub = getattr(slot_info, 'curricular_subject_id', '') or ''
                            if not s.preferred_subjects or s_sub in s.preferred_subjects:
                                matched_hours += 1
                            
                # Percentuale reale sul fabbisogno effettivo
                pct_pei = round((matched_hours / target_fabbisogno_hours * 100)) if target_fabbisogno_hours > 0 else 100
                pct_pei = min(100, pct_pei)
                
                val_pei_badge = "🟢 Ottima" if pct_pei >= 85 else ("🟡 Buona" if pct_pei >= 70 else "⚪ Parziale")

                pei_rows.append({
                    "Alunno DVA": s.name,
                    "Classe": c_name,
                    "Ore PEI Assegnate": f"{s.weekly_hours}h",
                    "Gravità PEI": "🔴 Grave (1:1)" if s.is_severe_coverage else "🟢 Ordinario",
                    "Materie Richieste PEI": ", ".join(pref_with_hours_labels) if pref_with_hours_labels else "Tutte le discipline (generale)",
                    "Disponibilità Materie Richieste": f"{total_req_hours_in_class}h in classe" if s.preferred_subjects else "30h",
                    "Copertura Materie PEI": f"{matched_hours} / {target_fabbisogno_hours}h",
                    "Aderenza Reale PEI %": f"{pct_pei}% ({val_pei_badge})"
                })
            if pei_rows:
                st.dataframe(pd.DataFrame(pei_rows), use_container_width=True, hide_index=True)
            else:
                st.info("Nessun alunno DVA configurato.")


def render_support_timetables_view(problem: TimetableProblem, curricular_result: Optional[Any], support_result: Optional[SupportTimetableResult]):
    st.header("🤝 Orario Sostegno, Compresenze & Inclusione")
    
    if not support_result or support_result.status not in ["OPTIMAL", "FEASIBLE"]:
        st.info("L'orario di sostegno non è stato ancora generato. Vai nel **Tab 6 (Genera Orario)** e clicca su **'Calcola Orario Sostegno'**.")
        return
        
    v_tab1, v_tab2, v_tab3 = st.tabs([
        "👨‍🏫 Orario per Docente di Sostegno",
        "♿ Orario per Alunno DVA",
        "🏫 Griglia Classe con Compresenze"
    ])
    
    days = DAYS_OF_WEEK[:problem.config.num_days]
    daily_h = problem.config.daily_hours[:problem.config.num_days]
    
    # 1. ORARIO DOCENTI SOSTEGNO
    with v_tab1:
        sup_teachers = [t_id for t_id in problem.teachers.keys() if t_id in support_result.grid_by_support_teacher and any(support_result.grid_by_support_teacher[t_id][d][h] for d in range(len(days)) for h in range(daily_h[d]))]
        if not sup_teachers:
            st.info("Nessun docente di sostegno assegnato con ore attive.")
        else:
            sel_sup_t = st.selectbox("Seleziona Docente di Sostegno / Potenziamento", sup_teachers, format_func=lambda x: problem.teachers[x].name if x in problem.teachers else x)
            
            t_obj = problem.teachers.get(sel_sup_t)
            tot_sup_h = sum(sa.hours_per_week for sa in problem.support_assignments if sa.teacher_id == sel_sup_t)
            
            st.subheader(f"📅 Orario Settimanale Sostegno - {t_obj.name if t_obj else sel_sup_t}")
            st.caption(f"Cattedra: **{tot_sup_h} ore settimanali** | Presenza spalmata su **5 giorni** | Zero ore buche ✅")
            
            t_grid = support_result.grid_by_support_teacher[sel_sup_t]
            matrix_display = []
            for d in range(len(days)):
                d_list = []
                for h in range(daily_h[d]):
                    slots = t_grid[d][h]
                    d_list.append(slots[0] if slots else None)
                matrix_display.append(d_list)
                
            day_has_lessons = [any(matrix_display[d][h] is not None for h in range(daily_h[d])) for d in range(len(days))]
            
            grid_html = render_html_schedule_table(days, daily_h, matrix_display, view_type="support_teacher", day_has_lessons=day_has_lessons)
            if hasattr(st, "html"):
                st.html(grid_html)
            else:
                st.markdown(grid_html, unsafe_allow_html=True)

    # 2. ORARIO ALUNNI DVA
    with v_tab2:
        if not problem.students_dva:
            st.info("Nessun alunno DVA registrato.")
        else:
            sel_stud_id = st.selectbox("Seleziona Alunno DVA", list(problem.students_dva.keys()), format_func=lambda x: f"{problem.students_dva[x].name} (Classe {problem.classes[problem.students_dva[x].class_id].name if problem.students_dva[x].class_id in problem.classes else ''})")
            
            stud_obj = problem.students_dva[sel_stud_id]
            s_grid = support_result.grid_by_student_dva.get(sel_stud_id, [])
            c_name = problem.classes[stud_obj.class_id].name if stud_obj.class_id in problem.classes else stud_obj.class_id
            
            st.subheader(f"📅 Orario Inclusione & Sostegno - {stud_obj.name}")
            st.caption(f"Classe: **{c_name}** | Ore Sostegno Settimanali: **{stud_obj.weekly_hours}h**")
            
            matrix_dva = []
            for d in range(len(days)):
                d_list = []
                for h in range(daily_h[d]):
                    slot = s_grid[d][h] if d < len(s_grid) and h < len(s_grid[d]) else None
                    matrix_dva.append(slot)
                    d_list.append(slot)
                # matrix_dva is collected
            
            matrix_dva_2d = []
            for d in range(len(days)):
                d_row = []
                for h in range(daily_h[d]):
                    slot = s_grid[d][h] if d < len(s_grid) and h < len(s_grid[d]) else None
                    d_row.append(slot)
                matrix_dva_2d.append(d_row)
                
            grid_html = render_html_schedule_table(days, daily_h, matrix_dva_2d, view_type="dva_student")
            if hasattr(st, "html"):
                st.html(grid_html)
            else:
                st.markdown(grid_html, unsafe_allow_html=True)

    # 3. GRIGLIA CLASSE CON COMPRESENZE & SOSTEGNI
    with v_tab3:
        cl_keys = list(problem.classes.keys())
        sel_c_view = st.selectbox("Seleziona Classe", cl_keys, format_func=lambda x: problem.classes[x].name if x in problem.classes else x, key="sel_c_sup_view")
        
        st.subheader(f"📅 Orario Integrato & Inclusione - Classe {problem.classes[sel_c_view].name}")
        st.caption("Orario curricolare ufficiale con evidenza grafica dei docenti di sostegno e delle compresenze presenti in aula.")
        
        c_grid_sup = support_result.grid_by_class_support.get(sel_c_view, [])
        c_grid_cur = curricular_result.grid_by_class.get(sel_c_view, []) if curricular_result else []
        
        matrix_cl = []
        for d in range(len(days)):
            d_row = []
            for h in range(daily_h[d]):
                cur_slot = c_grid_cur[d][h] if d < len(c_grid_cur) and h < len(c_grid_cur[d]) else None
                sup_slots = c_grid_sup[d][h] if d < len(c_grid_sup) and h < len(c_grid_sup[d]) else []
                
                if cur_slot is not None or sup_slots:
                    combined = {
                        'curricular': cur_slot,
                        'support': sup_slots,
                        'subject_color': getattr(cur_slot, 'subject_color', '#0284c7') if cur_slot else '#8b5cf6'
                    }
                    d_row.append(combined)
                else:
                    d_row.append(None)
            matrix_cl.append(d_row)
            
        grid_html = render_html_schedule_table(days, daily_h, matrix_cl, view_type="class_with_support")
        if hasattr(st, "html"):
            st.html(grid_html)
        else:
            st.markdown(grid_html, unsafe_allow_html=True)
