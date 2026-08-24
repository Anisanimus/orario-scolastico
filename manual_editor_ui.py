"""Modulo UI per i ritocchi manuali, smart swap e upload orario Excel con validazione."""
import streamlit as st
from typing import Dict, List, Optional, Tuple, Any
from models import TimetableProblem
from solver import TimetableResult, LessonSlotInfo

SlotInfo = LessonSlotInfo
import importlib
import manual_editor_engine
importlib.reload(manual_editor_engine)
from manual_editor_engine import apply_direct_swap, find_smart_repair_proposals, _rebuild_result_views
import schedule_importer
importlib.reload(schedule_importer)
from schedule_importer import import_timetable_from_excel
from schedule_renderer import render_html_schedule_table

def render_manual_editor_and_import_panel(problem: TimetableProblem):
    """Pannello interattivo per ritocchi manuali, Smart Repair e importazione/audit da Excel."""
    st.markdown("### ✏️ Ritocchi Manuali, Riparazione Smart & Importazione Orario")
    st.caption("Modifica l'orario curricolare prima di generare il sostegno: sposta manualmente le lezioni, chiedi al motore di proporre scambi a catena senza conflitti o carica un file Excel con audit immediato.")
    
    tab_edit, tab_upload = st.tabs([
        "✏️ 1. Ritocco Manuale & Smart Swap",
        "📥 2. Carica Orario da Excel (Audit Conflitti)"
    ])
    
    days = getattr(problem.config, "active_days", None) or getattr(problem.config, "days", ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])[:problem.config.num_days]
    daily_h = getattr(problem.config, "daily_hours", [6]*5)[:problem.config.num_days]
    
    # -------------------------------------------------------------
    # SUB-TAB 1: RITOCCO MANUALE & SMART SWAP
    # -------------------------------------------------------------
    with tab_edit:
        res: Optional[TimetableResult] = st.session_state.get("result")
        if not res or res.status not in ["OPTIMAL", "FEASIBLE", "IMPORTED"]:
            st.info("💡 Genera prima l'orario nella scheda **🚀 6. Genera Orario** oppure carica un file Excel per abilitare i ritocchi manuali.")
            return
            
        # Storico modifiche per Undo
        if "timetable_history" not in st.session_state:
            st.session_state.timetable_history = []
            
        c_head1, c_head2 = st.columns([3, 1])
        with c_head1:
            st.markdown("##### 🔄 Seleziona Classe e Slot da Spostare / Scambiare")
        with c_head2:
            if st.session_state.timetable_history:
                if st.button("↩️ Annulla Ultima Modifica", use_container_width=True):
                    st.session_state.result = st.session_state.timetable_history.pop()
                    st.success("Modifica annullata con successo!")
                    st.rerun()

        # Selezione Classe
        class_keys = list(problem.classes.keys())
        sel_c_id = st.selectbox(
            "Seleziona la Classe su cui operare:",
            class_keys,
            format_func=lambda x: problem.classes[x].name if x in problem.classes else x,
            key="sb_manual_class"
        )
        
        c_grid = res.grid_by_class.get(sel_c_id, [])
        if not c_grid:
            st.warning("Griglia classe non trovata.")
            return
            
        # Anteprima Griglia Classe Corrente
        matrix_c = []
        for d in range(len(days)):
            d_row = []
            for h in range(daily_h[d]):
                d_row.append(c_grid[d][h] if d < len(c_grid) and h < len(c_grid[d]) else None)
            matrix_c.append(d_row)
            
        st.markdown(f"**Orario Attuale Classe {problem.classes[sel_c_id].name}:**")
        html_preview = render_html_schedule_table(days, daily_h, matrix_c, view_type="class")
        if hasattr(st, "html"):
            st.html(html_preview)
        else:
            st.markdown(html_preview, unsafe_allow_html=True)
            
        st.divider()
        
        # Selezione Slot Origine e Slot Destinazione
        col_orig, col_dest = st.columns(2)
        with col_orig:
            st.markdown("##### 📍 1. Slot Origine (Da Spostare)")
            orig_day = st.selectbox("Giorno Origine", list(range(len(days))), format_func=lambda d: days[d], key="sb_orig_day")
            orig_max_h = daily_h[orig_day]
            orig_hour = st.selectbox("Ora Origine", list(range(orig_max_h)), format_func=lambda h: f"{h+1}ª Ora", key="sb_orig_h")
            
            orig_slot: Optional[SlotInfo] = c_grid[orig_day][orig_hour] if orig_day < len(c_grid) and orig_hour < len(c_grid[orig_day]) else None
            if orig_slot:
                st.info(f"📖 **{orig_slot.subject_name}** | 👤 {orig_slot.teacher_name} | 📍 {orig_slot.room_name or 'Aula ordinaria'}")
            else:
                st.info("⚪ *Ora Libera*")
                
        with col_dest:
            st.markdown("##### 🎯 2. Slot Destinazione (Scambia con)")
            dest_day = st.selectbox("Giorno Destinazione", list(range(len(days))), format_func=lambda d: days[d], key="sb_dest_day")
            dest_max_h = daily_h[dest_day]
            dest_hour = st.selectbox("Ora Destinazione", list(range(dest_max_h)), format_func=lambda h: f"{h+1}ª Ora", key="sb_dest_h")
            
            dest_slot: Optional[SlotInfo] = c_grid[dest_day][dest_hour] if dest_day < len(c_grid) and dest_hour < len(c_grid[dest_day]) else None
            if dest_slot:
                st.info(f"📖 **{dest_slot.subject_name}** | 👤 {dest_slot.teacher_name} | 📍 {dest_slot.room_name or 'Aula ordinaria'}")
            else:
                st.info("⚪ *Ora Libera*")

        if orig_day == dest_day and orig_hour == dest_hour:
            st.warning("⚠️ Origine e destinazione coincidono. Seleziona due slot diversi.")
        else:
            # Simulazione Scambio Diretto e Verifica Conflitti
            test_res, test_report = apply_direct_swap(problem, res, sel_c_id, orig_day, orig_hour, dest_day, dest_hour)
            
            st.write("")
            if test_report.is_valid:
                st.success(f"🟢 **Scambio Diretto Valido al 100%!** Nessuna sovrapposizione rilevata per docenti, classi o aule.")
                if st.button("✅ Applica Scambio Diretto", type="primary", use_container_width=True, key="btn_apply_direct_swap"):
                    import copy
                    st.session_state.timetable_history.append(copy.deepcopy(st.session_state.result))
                    st.session_state.result = test_res
                    st.toast("Scambio applicato con successo!", icon="✅")
                    st.rerun()
            else:
                st.error(f"🔴 **Conflitto Rilevato per lo Scambio Diretto ({test_report.total_errors} errori):**")
                for err in test_report.issues:
                    if err.issue_type == "ERROR":
                        st.markdown(f"- ❌ **{err.title}**: {err.description}")
                        
                st.markdown("---")
                st.markdown("#### 🤖 Assistente Riparazione Smart (Trova Soluzioni Alternative)")
                st.caption("Il motore matematico CP-SAT cercherà automaticamente la catena minima di spostamenti a cascata per permettere questo cambio senza alcun conflitto.")
                
                if orig_slot:
                    if st.button(f"🔍 Trova Catena di Scambi per Spostare {orig_slot.subject_name} a {days[dest_day]} ({dest_hour+1}ª ora)", type="primary", use_container_width=True, key="btn_find_smart_repair"):
                        with st.spinner("Calcolo combinazioni ottimali di scambio in corso (1-3 sec)..."):
                            proposals = find_smart_repair_proposals(
                                problem, res, sel_c_id, dest_day, dest_hour, 
                                orig_slot.subject_id, 
                                orig_assignment_id=getattr(orig_slot, "assignment_id", None),
                                time_limit_sec=10
                            )
                            st.session_state.current_repair_proposals = proposals
                            if not proposals:
                                st.session_state.smart_repair_failed_msg = True
                            else:
                                st.session_state.pop("smart_repair_failed_msg", None)
                            
                    if st.session_state.get("smart_repair_failed_msg"):
                        st.warning("⚠️ **Nessuna catena di scambio lecita trovata**: lo spostamento richiesto viola un vincolo rigido invalicabile (es. il docente o l'aula è totalmente indisponibile in quell'ora o c'è un parallelismo attivo bloccato). Prova a selezionare un'altra ora o un altro giorno.")
                            
                    if "current_repair_proposals" in st.session_state and st.session_state.current_repair_proposals:
                        proposals = st.session_state.current_repair_proposals
                        st.markdown(f"##### ✨ Proposte di Riparazione Trovate ({len(proposals)} opzioni):")
                        for idx, prop in enumerate(proposals):
                            with st.expander(f"⭐ **Opzione {idx+1}: {prop.description}**", expanded=True):
                                st.write("Elenco spostamenti previsti:")
                                for chg in prop.changes_details:
                                    st.markdown(f"- 🔄 `{chg}`")
                                    
                                if prop.report.is_valid:
                                    st.success("🟢 Risultato finale: 0 conflitti, 100% conforme a vincoli didattici!")
                                else:
                                    st.warning(f"⚠️ {prop.report.total_warnings} avvisi minori.")
                                    
                                if st.button(f"🚀 Applica Opzione {idx+1}", key=f"btn_apply_prop_{idx}", type="primary"):
                                    import copy
                                    st.session_state.timetable_history.append(copy.deepcopy(st.session_state.result))
                                    st.session_state.result = prop.resulting_result
                                    del st.session_state.current_repair_proposals
                                    st.toast("Riparazione smart applicata con successo!", icon="🎉")
                                    st.rerun()

    # -------------------------------------------------------------
    # SUB-TAB 2: UPLOAD ORARIO EXCEL & AUDIT ERRORI
    # -------------------------------------------------------------
    with tab_upload:
        st.subheader("📥 Carica Orario Curricolare Ritoccato da Excel (.xlsx)")
        st.write("Puoi caricare un orario ritoccato o compilato esternamente in Excel. L'algoritmo effettuerà un **audit completo di conformità** (sovrapposizioni docenti, aule, ore per materia, carichi giornalieri).")
        
        uploaded_f = st.file_uploader("Seleziona Cartella Excel Orario (.xlsx)", type=["xlsx"], key="upl_manual_timetable_excel")
        if uploaded_f is not None:
            with st.spinner("Parsing del file Excel e verifica conflitti in corso..."):
                imp_res, imp_report, imp_logs = import_timetable_from_excel(uploaded_f.getvalue(), problem)
                
            if imp_logs:
                with st.expander("📋 Log di Lettura e Riconoscimento Fogli/Classi", expanded=False):
                    for l in imp_logs:
                        st.markdown(f"- {l}")
                        
            if imp_res:
                st.divider()
                st.markdown("#### 🔍 Risultato Audit di Conformità e Conflitti")
                
                c_stat1, c_stat2, c_stat3 = st.columns(3)
                c_stat1.metric("Stato Orario", "🟢 VALIDO (Zero Errori)" if imp_report.is_valid else "🔴 CONFLITTI RILEVATI")
                c_stat2.metric("Errori Bloccanti", imp_report.total_errors)
                c_stat3.metric("Avvisi / Desiderata", imp_report.total_warnings)
                
                if not imp_report.is_valid:
                    st.error(f"❌ Sono stati riscontrati **{imp_report.total_errors} errori bloccanti**. Risolvili o correggili prima di utilizzarlo per il sostegno.")
                    for err in imp_report.issues:
                        if err.issue_type == "ERROR":
                            st.markdown(f"- 🔴 **[{err.category}] {err.title}**: {err.description}")
                            
                if imp_report.total_warnings > 0:
                    with st.expander(f"⚠️ Visualizza {imp_report.total_warnings} Avvisi e Preferenze Non Rispettate", expanded=False):
                        for w in imp_report.issues:
                            if w.issue_type == "WARNING":
                                st.markdown(f"- 🟡 **[{w.category}] {w.title}**: {w.description}")
                                
                if imp_report.is_valid:
                    st.success("🎉 L'orario caricato è perfettamente valido e coerente con tutte le cattedre, docenti e aule della scuola!")
                    
                if st.button("📌 Imposta come Orario Curricolare Ufficiale (Attivo per il Sostegno)", type="primary", use_container_width=True, key="btn_activate_imported_timetable"):
                    st.session_state.result = imp_res
                    st.toast("Orario importato e attivato con successo!", icon="✅")
                    st.rerun()
