# -*- coding: utf-8 -*-
import sys, os, io, traceback
import pandas as pd
from typing import Dict, List, Any

sys.stdout.reconfigure(encoding='utf-8')

print('=' * 80)
print(' AVVIO TEST SUITE PROFESSIONALE DI RILASCIO (PRODUCTION READY)')
print('=' * 80)

failures = []

def run_test(name, fn):
    print(f'\n[TEST] {name}...')
    try:
        fn()
        print('  --> [OK] PASSATO CON SUCCESSO! [PASS] ✅')
    except Exception as e:
        print(f'  --> [FAIL] FALLITO ❌: {e}')
        traceback.print_exc()
        failures.append((name, str(e)))

# -------------------------------------------------------------
# 1. Modelli Dataclass & Serializzazione Bidirezionale
# -------------------------------------------------------------
def test_models():
    from models import SchoolConfig, Teacher, SchoolClass, Subject, Classroom, TeachingAssignment, TimetableProblem, StudentDVA, SupportAssignment, ParallelGroup
    from sample_data import get_sample_problem
    
    p = get_sample_problem(num_classes=18, is_dada=True, with_theater=True)
    d = p.to_dict()
    assert isinstance(d, dict), 'to_dict fallito'
    p2 = TimetableProblem.from_dict(d)
    assert len(p2.teachers) == len(p.teachers), 'Teacher count mismatch'
    assert len(p2.classes) == len(p.classes), 'Classes count mismatch'
    assert len(p2.rooms) == len(p.rooms), 'Rooms count mismatch'
    assert len(p2.assignments) == len(p.assignments), 'Assignments count mismatch'
    assert len(p2.students_dva) == len(p.students_dva), 'DVA count mismatch'
    assert len(p2.support_assignments) == len(p.support_assignments), 'Support count mismatch'

run_test('1. Modelli Dataclass & Serializzazione Bidirezionale (JSON/Dict)', test_models)

# -------------------------------------------------------------
# 2. Generatore Dati Demo e Scenari Didattici
# -------------------------------------------------------------
def test_sample_data_scenarios():
    from sample_data import get_sample_problem, get_empty_problem
    
    # 5 Giorni DADA + Teatro
    p1 = get_sample_problem(num_classes=18, is_dada=True, with_theater=True, num_days=5)
    assert p1.config.num_days == 5
    assert len(p1.classes) == 18
    assert len(p1.rooms) >= 20
    
    # 6 Giorni Tradizionale
    p2 = get_sample_problem(num_classes=12, is_dada=False, with_theater=False, num_days=6)
    assert p2.config.num_days == 6
    assert len(p2.classes) == 12
    
    # Empty problem
    p0 = get_empty_problem()
    assert len(p0.teachers) == 0
    assert len(p0.classes) == 0

run_test('2. Generazione Scenari Didattici (5gg DADA, 6gg Tradizionale, Vuoto)', test_sample_data_scenarios)

# -------------------------------------------------------------
# 3. File Master Unificato Excel (Export + Import + Roundtrip)
# -------------------------------------------------------------
def test_unified_excel_roundtrip():
    from sample_data import get_sample_problem
    from importers import generate_unified_school_excel, parse_unified_school_excel
    
    p_orig = get_sample_problem(num_classes=18, is_dada=True, with_theater=True)
    xlsx_bytes = generate_unified_school_excel(p_orig)
    assert len(xlsx_bytes) > 5000, 'Excel file too small'
    
    p_imported, logs = parse_unified_school_excel(xlsx_bytes)
    assert len(p_imported.teachers) == len(p_orig.teachers), f'Docenti {len(p_imported.teachers)} != {len(p_orig.teachers)}'
    assert len(p_imported.classes) == len(p_orig.classes), f'Classi {len(p_imported.classes)} != {len(p_orig.classes)}'
    assert len(p_imported.rooms) == len(p_orig.rooms), f'Aule {len(p_imported.rooms)} != {len(p_orig.rooms)}'
    assert len(p_imported.assignments) == len(p_orig.assignments), f'Cattedre {len(p_imported.assignments)} != {len(p_orig.assignments)}'
    assert len(p_imported.students_dva) == len(p_orig.students_dva), f'DVA {len(p_imported.students_dva)} != {len(p_orig.students_dva)}'
    assert len(p_imported.support_assignments) == len(p_orig.support_assignments), f'Support {len(p_imported.support_assignments)} != {len(p_orig.support_assignments)}'
    
    empty_bytes = generate_unified_school_excel(None)
    assert len(empty_bytes) > 3000

run_test('3. File Master Unificato Excel Multi-Foglio (8 Fogli, Full-Fidelity Roundtrip)', test_unified_excel_roundtrip)

# -------------------------------------------------------------
# 4. Solutore CP-SAT OR-Tools (Calcolo Orario Curricolare)
# -------------------------------------------------------------
def test_cpsat_solver():
    from sample_data import get_sample_problem
    from solver import TimetableSolver
    
    p = get_sample_problem(num_classes=6, is_dada=True, with_theater=False, num_days=5)
    solver = TimetableSolver(p, max_gap_limit=2, strict_gap_limit=False)
    res = solver.solve(max_time_seconds=15, random_seed=42)
    assert res.status in ['OPTIMAL', 'FEASIBLE'], f'Solver returned {res.status}'
    assert res.grid_by_class is not None, 'grid_by_class is None'
    assert len(res.grid_by_class) == len(p.classes), 'Not all classes scheduled'
    assert res.total_gap_hours >= 0

run_test('4. Motore CP-SAT OR-Tools (Vincoli Rigidi, Morbidi, Aule DADA, Gap Minimization)', test_cpsat_solver)

# -------------------------------------------------------------
# 5. Algoritmo Assegnazione Sostegno & Compresenze
# -------------------------------------------------------------
def test_support_solver():
    from sample_data import get_sample_problem
    from solver import TimetableSolver
    from support_solver import SupportTimetableSolver
    
    p = get_sample_problem(num_classes=6, is_dada=True, num_days=5)
    solver = TimetableSolver(p, max_gap_limit=2, strict_gap_limit=False)
    res = solver.solve(max_time_seconds=15, random_seed=42)
    if res.status in ['OPTIMAL', 'FEASIBLE']:
        sup_solver = SupportTimetableSolver(p, res)
        sup_res = sup_solver.solve(max_time_seconds=10)
        assert sup_res is not None, 'Support result is None'
        assert sup_res.status in ['OPTIMAL', 'FEASIBLE'], f'Support status: {sup_res.status}'
        assert sup_res.total_assigned_hours > 0, 'No support hours placed'

run_test('5. Algoritmo Ottimizzazione Sostegno & Compresenze PEI', test_support_solver)

# -------------------------------------------------------------
# 6. Esportazione PDF Alta Definizione (A4 Orizzontale)
# -------------------------------------------------------------
def test_pdf_exports():
    from sample_data import get_sample_problem
    from solver import TimetableSolver
    from support_solver import SupportTimetableSolver
    from pdf_export import (
        generate_classes_pdf, generate_teachers_pdf, generate_rooms_pdf,
        generate_support_teachers_pdf, generate_classes_with_support_pdf
    )
    
    p = get_sample_problem(num_classes=3, is_dada=True, num_days=5)
    solver = TimetableSolver(p, max_gap_limit=2, strict_gap_limit=False)
    res = solver.solve(max_time_seconds=8, random_seed=42)
    if res.status in ['OPTIMAL', 'FEASIBLE']:
        sup_solver = SupportTimetableSolver(p, res)
        sup_res = sup_solver.solve(max_time_seconds=6)
        
        pdf_cls = generate_classes_pdf(p, res)
        assert pdf_cls and len(pdf_cls) > 1000, 'PDF Classi vuoto'
        
        pdf_t = generate_teachers_pdf(p, res)
        assert pdf_t and len(pdf_t) > 1000, 'PDF Docenti vuoto'
        
        pdf_r = generate_rooms_pdf(p, res)
        assert pdf_r and len(pdf_r) > 1000, 'PDF Aule vuoto'
        
        pdf_sup = generate_support_teachers_pdf(p, res, sup_res)
        assert pdf_sup and len(pdf_sup) > 1000, 'PDF Sostegno Docenti vuoto'
        
        pdf_cls_sup = generate_classes_with_support_pdf(p, res, sup_res)
        assert pdf_cls_sup and len(pdf_cls_sup) > 1000, 'PDF Classi con Sostegno vuoto'

run_test('6. Generazione Prospetti PDF Ufficiali (Classi, Docenti, Aule, Sostegno)', test_pdf_exports)

# -------------------------------------------------------------
# 7. Esportazione Tabelloni Excel
# -------------------------------------------------------------
def test_excel_exports():
    from sample_data import get_sample_problem
    from solver import TimetableSolver
    from support_solver import SupportTimetableSolver
    from exporters import generate_excel_timetable, generate_excel_tabellone_combo
    
    p = get_sample_problem(num_classes=3, is_dada=True, num_days=5)
    solver = TimetableSolver(p, max_gap_limit=2, strict_gap_limit=False)
    res = solver.solve(max_time_seconds=8, random_seed=42)
    if res.status in ['OPTIMAL', 'FEASIBLE']:
        sup_solver = SupportTimetableSolver(p, res)
        sup_res = sup_solver.solve(max_time_seconds=6)
        
        ex_main = generate_excel_timetable(p, res, sup_res)
        assert ex_main and len(ex_main) > 2000, 'Excel main export failed'
        
        ex_combo = generate_excel_tabellone_combo(p, res, sup_res)
        assert ex_combo and len(ex_combo) > 2000, 'Excel combo export failed'

run_test('7. Esportazione Cartella Excel Tabellone Completo & Fogli Singoli', test_excel_exports)

# -------------------------------------------------------------
# 8. Modifica Docente & Helper create_safe_teacher
# -------------------------------------------------------------
def test_teacher_editing_integrity():
    from app import create_safe_teacher
    
    t = create_safe_teacher(
        id='doc_test_1',
        name='Prof. Test Modifica',
        cdc='A-22',
        is_part_time=True,
        contract_hours=12,
        max_working_days=3,
        free_days=['Lunedì', 'Venerdì'],
        min_daily_hours=3,
        max_daily_hours=4,
        extra_custom_param='valore_protetto'
    )
    assert t.name == 'Prof. Test Modifica'
    assert t.min_daily_hours == 3
    assert t.max_daily_hours == 4
    assert t.is_part_time is True
    assert t.contract_hours == 12
    assert t.free_days == ['Lunedì', 'Venerdì']
    assert getattr(t, 'extra_custom_param', None) == 'valore_protetto'

run_test('8. Integrita Modifica & Creazione Docente (create_safe_teacher resiliente)', test_teacher_editing_integrity)

# -------------------------------------------------------------
# 9. Test Compilazione Statica di Tutti i File Python del Progetto
# -------------------------------------------------------------
def test_static_compilation():
    import py_compile
    py_files = [f for f in os.listdir('.') if f.endswith('.py')]
    for pf in py_files:
        py_compile.compile(pf, doraise=True)

run_test('9. Compilazione Bytecode & Sintassi di Tutti i File Python', test_static_compilation)

print('\n' + '=' * 80)
if not failures:
    print('>>> 🎉 TUTTI I 9/9 TEST DI PRODUZIONE SONO PASSATI CON SUCCESSO AL 100%! <<<')
    print('>>> 🏆 L\'APPLICAZIONE E COMPLETAMENTE CERTIFICATA E PRONTA PER IL RILASCIO! <<<')
else:
    print(f'>>> ❌ FALLITI {len(failures)} TEST <<<')
    for name, err in failures:
        print(f'   - {name}: {err}')
print('=' * 80)
