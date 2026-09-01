import unittest
import time
from models import TimetableProblem, SchoolConfig, Teacher, SchoolClass, Subject, Classroom, TeachingAssignment
from sample_data import get_sample_problem, get_empty_problem
from solver import TimetableSolver, TimetableResult

class ComprehensiveScenarioAndCouplingTest(unittest.TestCase):
    
    def _test_solve(self, problem: TimetableProblem, scenario_name: str, max_time: int = 15):
        print(f"\n[TEST] Risoluzione scenario: {scenario_name} (Classi: {len(problem.classes)}, Docenti: {len(problem.teachers)}, Aule: {len(problem.rooms)})...")
        t0 = time.time()
        solver = TimetableSolver(problem)
        result = solver.solve(max_time_seconds=max_time)
        dt = time.time() - t0
        print(f" -> Stato: {result.status} in {dt:.2f}s | Ore buche: {result.total_gap_hours}h")
        self.assertIn(result.status, ["OPTIMAL", "FEASIBLE"], f"Fallimento orario per scenario {scenario_name}: {result.status}")
        self.assertIsNotNone(result.grid_by_class)
        self.assertIsNotNone(result.grid_by_teacher)
        self.assertEqual(len(result.grid_by_class), len(problem.classes))
        return result

    def test_1_standard_5days(self):
        prob = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        self._test_solve(prob, "Standard 5 Giorni (18 Classi)")

    def test_2_standard_6days(self):
        prob = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=6, with_musical_curriculum=False, with_extended_curriculum=False)
        self._test_solve(prob, "Standard 6 Giorni Lun-Sab (18 Classi + Giorno Libero)")

    def test_3_dada_standard(self):
        prob = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        self._test_solve(prob, "Modello DADA Standard (26 Aule Disciplinari)")

    def test_4_dada_theater(self):
        prob = get_sample_problem(num_classes=18, is_dada=True, with_theater=True, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        self._test_solve(prob, "DADA + Laboratorio Teatro (18 Classi)")

    def test_5_musical_curriculum_32h(self):
        prob = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=True, with_extended_curriculum=False)
        self._test_solve(prob, "Indirizzo Musicale 32h Corso F con Orchestra in compresenza")

    def test_6_extended_curriculum_36h(self):
        prob = get_sample_problem(num_classes=18, is_dada=False, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=True)
        self._test_solve(prob, "Tempo Prolungato 36h Corso E con 2 Rientri e Compresenze")

    def test_7_dada_with_max_accorpamento(self):
        prob = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        # Simula click su "Massimo Accorpamento (Tutte >= 2h)"
        for s_id in prob.subjects:
            prob.config.subject_block_preferences[s_id] = True
        for a in prob.assignments:
            if a.hours_per_week >= 2:
                a.force_double_hours = True
                a.max_daily_hours = 2 if a.hours_per_week <= 5 else 4
        self._test_solve(prob, "DADA con Massimo Accorpamento (Tutte >= 2h)")

    def test_8_dada_with_all_single_hours(self):
        prob = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        # Simula click su "Tutte Ore Singole Separate"
        for s_id in prob.subjects:
            prob.config.subject_block_preferences[s_id] = False
        for a in prob.assignments:
            a.force_double_hours = False
            a.max_daily_hours = 1 if a.hours_per_week in [2, 3] else 2
        self._test_solve(prob, "DADA con Tutte Ore Singole Separate")

    def test_9_dada_with_only_labs_blocks(self):
        prob = get_sample_problem(num_classes=18, is_dada=True, with_theater=False, num_days=5, with_musical_curriculum=False, with_extended_curriculum=False)
        # Simula click su "Solo Laboratori (Arte, Tec, Mot, Mus)"
        for s_id in prob.subjects:
            val = (s_id in ["art", "tec", "mot", "mus"])
            prob.config.subject_block_preferences[s_id] = val
        for a in prob.assignments:
            should_c = prob.config.subject_block_preferences.get(a.subject_id, False)
            if should_c and a.hours_per_week >= 2:
                a.force_double_hours = True
                a.max_daily_hours = 2
            else:
                a.force_double_hours = False
                a.max_daily_hours = 1 if a.hours_per_week in [2, 3] else 2
        self._test_solve(prob, "DADA con Solo Laboratori Accorpati")

if __name__ == "__main__":
    unittest.main()
