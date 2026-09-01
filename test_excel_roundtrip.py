import unittest
import io
import pandas as pd
from sample_data import get_sample_problem
from importers import generate_unified_school_excel, parse_unified_school_excel, generate_excel_template, parse_excel_timetable
from exporters import generate_excel_timetable, generate_excel_tabellone_combo
from solver import TimetableSolver

class ExcelImportExportTest(unittest.TestCase):

    def test_1_unified_school_excel_roundtrip(self):
        print("\n[TEST EXCEL] 1. Test Esportazione / Importazione Excel Master Completo (18 Classi)...")
        prob_orig = get_sample_problem(num_classes=18, is_dada=True, with_theater=True, num_days=5)
        
        # 1. Genera bytes Excel Master
        excel_bytes = generate_unified_school_excel(prob_orig)
        self.assertIsNotNone(excel_bytes)
        self.assertGreater(len(excel_bytes), 1000)
        
        # 2. Rileggi e Parsea il file Excel generato
        excel_file = io.BytesIO(excel_bytes)
        prob_reloaded, logs = parse_unified_school_excel(excel_file)
        
        print(f" -> Log importazione: {len(logs)} messaggi")
        self.assertEqual(len(prob_reloaded.classes), len(prob_orig.classes), "Numero classi non corrisponde dopo import")
        self.assertEqual(len(prob_reloaded.teachers), len(prob_orig.teachers), "Numero docenti non corrisponde dopo import")
        self.assertEqual(len(prob_reloaded.assignments), len(prob_orig.assignments), "Numero cattedre non corrisponde dopo import")
        print(" -> [OK] Roundtrip Excel Master SUPERATO con successo!")

    def test_2_timetable_generation_excel_exports(self):
        print("\n[TEST EXCEL] 2. Test Esportazione Tabellone Orario Generato (Classi, Docenti, Combo)...")
        prob = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5)
        solver = TimetableSolver(prob)
        result = solver.solve(max_time_seconds=15)
        
        self.assertIn(result.status, ["OPTIMAL", "FEASIBLE"])
        
        # Test export tabellone orario completo (Classi e Docenti)
        b_full = generate_excel_timetable(prob, result)
        self.assertIsNotNone(b_full)
        self.assertGreater(len(b_full), 1000)

        # Test export tabellone combo ministeriale
        b_combo = generate_excel_tabellone_combo(prob, result)
        self.assertIsNotNone(b_combo)
        self.assertGreater(len(b_combo), 1000)
        
        print(" -> [OK] Esportazione di tutti i formati Excel orario SUPERATA con successo!")

if __name__ == "__main__":
    unittest.main()
