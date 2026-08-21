"""
Script di verifica e collaudo del solutore dell'orario scolastico (Test Tradizionale + DADA).
"""
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from sample_data import get_sample_problem
from solver import TimetableSolver
from exporters import generate_excel_timetable

def run_test(num_classes: int, is_dada: bool):
    label = f"{num_classes} CLASSI - {'MODELLO DADA' if is_dada else 'MODELLO TRADIZIONALE'}"
    print(f"\n==========================================")
    print(f" TEST SOLUTORE: {label}")
    print(f"==========================================")
    
    problem = get_sample_problem(num_classes=num_classes, is_dada=is_dada)
    print(f"1. Dati caricati:")
    print(f"   - Scuola: {problem.config.school_name}")
    print(f"   - Classi: {len(problem.classes)}")
    print(f"   - Docenti: {len(problem.teachers)}")
    print(f"   - Cattedre: {len(problem.assignments)}")
    print(f"   - Aule/Laboratori: {len(problem.rooms)}")

    # Test desiderata puntuali su giorni specifici
    if "doc_ita_1" in problem.teachers:
        problem.teachers["doc_ita_1"].late_entry_days = ["Lunedì", "Giovedì"]
    if "doc_mat_1" in problem.teachers:
        problem.teachers["doc_mat_1"].early_exit_days = ["Venerdì"]

    print(f"\n2. Risoluzione con OR-Tools (CP-SAT)...")
    solver = TimetableSolver(problem, max_gap_limit=6, strict_gap_limit=True)
    result = solver.solve(max_time_seconds=15)

    print(f"3. Risultato:")
    print(f"   - Stato: {result.status}")
    print(f"   - Tempo: {result.solve_time} s")
    print(f"   - Score Soddisfazione Globale: {result.global_satisfaction_score}%")
    print(f"   - Giorni liberi 1ª scelta: {result.free_days_satisfied_first} / {result.free_days_total_first}")
    print(f"   - Ore doppie didattiche: {result.double_hours_satisfied} / {result.double_hours_total}")
    print(f"   - Totale ore buche: {result.total_gap_hours}")
    print(f"   - Ingressi posticipati (No 1ª ora): {result.late_entry_satisfied} / {result.late_entry_total}")
    print(f"   - Uscite anticipate (No ult. ora): {result.early_exit_satisfied} / {result.early_exit_total}")
    print(f"   - Slot sconsigliati evitati: {result.soft_slots_satisfied} / {result.soft_slots_total}")
    
    assert result.status in ["OPTIMAL", "FEASIBLE"], f"Fallito test per {label} (Stato: {result.status})"

    # Verifica giorni effettivi per part-time
    for t_id, teacher in problem.teachers.items():
        if teacher.is_part_time and teacher.max_working_days is not None:
            days_count = sum(1 for d in range(problem.config.num_days) if any(result.grid_by_teacher[t_id][d][h] is not None for h in range(problem.config.daily_hours[d])))
            print(f"   - Part-Time {teacher.name.split()[1]}: lavora in {days_count} giorni (Max consentito: {teacher.max_working_days}) -> {'OK [V]' if days_count <= teacher.max_working_days else 'ERRORE'}")

    # Verifica limite massimo ore buche per ciascun docente (Max 6)
    max_gap_found = max(result.gaps_by_teacher.values()) if result.gaps_by_teacher else 0
    print(f"   - Massimo ore buche registrate per singolo docente: {max_gap_found}h (Limite consentito: ≤ 6h) -> OK [V]")
    for t_id, gaps in result.gaps_by_teacher.items():
        assert gaps <= 6, f"Docente {t_id} ha {gaps} ore buche (> 6 consentite!)"
    
    excel_bytes = generate_excel_timetable(problem, result)
    print(f"4. Excel generato: {len(excel_bytes)} bytes")
    
    # Verifica consecutività ore doppie forzate (es. Scienze Motorie e Musica a blocchi da 2h consecutive)
    for sub_chk_id, sub_label in [("mot", "Scienze Motorie"), ("mus", "Musica"), ("art", "Arte"), ("tec", "Tecnologia")]:
        chk_count = 0
        for a in problem.assignments:
            if a.subject_id == sub_chk_id and (a.force_double_hours or problem.config.subject_block_preferences.get(sub_chk_id, False)):
                days_with_hours = []
                for d in range(problem.config.num_days):
                    hours_in_day = [h for h in range(problem.config.daily_hours[d]) if result.grid_by_class[a.class_id][d][h] and result.grid_by_class[a.class_id][d][h].assignment_id == a.id]
                    if len(hours_in_day) == 2:
                        assert hours_in_day[1] == hours_in_day[0] + 1, f"Classe {a.class_id} ha 2 ore di {sub_label} NON consecutive: ore {hours_in_day}!"
                        days_with_hours.append(d)
                    elif len(hours_in_day) > 0:
                        assert False, f"Classe {a.class_id} ha {len(hours_in_day)} ore di {sub_label} nel giorno {d} anziché 2 ore consecutive!"
                assert len(days_with_hours) == 1, f"Classe {a.class_id} non ha esattamente 1 giorno con 2h consecutive di {sub_label}!"
                chk_count += 1
        if chk_count > 0:
            print(f"   - {sub_label} ({chk_count} classi): 100% in 1 BLOCCO DA 2 ORE CONSECUTIVE -> OK [V]")

    print(f"[OK] Test superato con successo per {label}!")

def main():
    run_test(num_classes=18, is_dada=False)
    print("\n🎉 TEST PER 18 CLASSI COMPLETATO CON SUCCESSO!")

if __name__ == "__main__":
    main()
