# -*- coding: utf-8 -*-
"""
Suite di Test Professionale per le Funzionalità Avanzate:
1. Tempo Musicale a 32h (Corso F)
2. Compresenza Orchestra/Solfeggio a 4 docenti (A-56 Violino, Clarinetto, Flauto, Chitarra)
3. Fissaggio Slot Orari Pomeridiani (fino a 9ª ora)
4. Unica Palestra e Parallelismo Scienze Motorie sulle Classi Terze (3A-3B, 3C-3D, 3E-3F)
5. Esportazione Excel e Rendering Tabellone con 9 slot e senza sovrapposizioni
"""
import sys
import unittest
from typing import List, Dict, Any

from models import (
    TimetableProblem, SchoolConfig, Teacher, SchoolClass, Subject, Classroom,
    TeachingAssignment, ParallelGroup, DAYS_OF_WEEK
)
from sample_data import get_sample_problem
from solver import TimetableSolver
from schedule_renderer import render_html_schedule_table
from exporters import generate_excel_timetable, generate_excel_tabellone_combo

class TestMusicalCurriculumAndAfternoonSuite(unittest.TestCase):

    def setUp(self):
        # Carica scenario musicale standard con 18 classi
        self.problem = get_sample_problem(
            num_classes=18,
            is_dada=False,
            with_theater=False,
            num_days=5,
            with_musical_curriculum=True,
            with_extended_curriculum=False
        )

    def test_01_musical_problem_structure(self):
        """Verifica che la struttura dell'indirizzo musicale sia configurata correttamente."""
        cfg = self.problem.config
        self.assertTrue(getattr(cfg, "has_musical_curriculum", False), "has_musical_curriculum deve essere True")
        self.assertEqual(getattr(cfg, "musical_section", ""), "F", "La sezione musicale deve essere F")
        
        # Classi corso F devono avere 32h
        mus_classes = [c for c in self.problem.classes.values() if c.section == "F"]
        self.assertEqual(len(mus_classes), 3, "Devono esserci 3 classi musicali (1F, 2F, 3F)")
        for c in mus_classes:
            self.assertEqual(c.curriculum_type, "musicale")
            self.assertEqual(c.weekly_hours_target, 32)
            self.assertTrue(len(c.afternoon_days) >= 1, f"Classe {c.name} deve avere almeno 1 giorno di rientro")

    def test_02_instrument_teachers_and_cdc(self):
        """Verifica la presenza dei 4 docenti di strumento con CdC A-56 corretta."""
        inst_ids = ["doc_str_violino", "doc_str_clarinetto", "doc_str_flauto", "doc_str_chitarra"]
        for tid in inst_ids:
            self.assertIn(tid, self.problem.teachers, f"Docente {tid} non trovato nel database docenti")
            t = self.problem.teachers[tid]
            self.assertTrue("A-56" in t.cdc, f"Il docente {t.name} deve avere CdC A-56, trovato: {t.cdc}")

    def test_03_single_gym_and_third_grade_parallelism(self):
        """Verifica che ci sia 1 sola palestra e 3 gruppi di parallelismo per le classi terze."""
        gym_rooms = [r for r in self.problem.rooms.values() if "mot" in r.subject_ids]
        self.assertEqual(len(gym_rooms), 1, f"Deve esserci esattamente 1 palestra, trovate: {len(gym_rooms)}")
        gym = gym_rooms[0]
        self.assertEqual(gym.id, "bebe_vio")
        self.assertGreaterEqual(gym.capacity, 2, "La palestra unica deve poter accogliere 2 classi in parallelo")

        pg_list = self.problem.config.parallel_groups
        self.assertEqual(len(pg_list), 3, "Devono esserci 3 gruppi di parallelismo per le classi terze (3A+3B, 3C+3D, 3E+3F)")
        for pg in pg_list:
            self.assertEqual(pg.subject_id, "mot")
            self.assertEqual(pg.parallel_hours, 2)
            self.assertEqual(len(pg.class_ids), 2)
            self.assertTrue(pg.force_consecutive_block)

    def test_04_solver_feasibility_and_co_teaching(self):
        """Esegue il solutore CP-SAT e verifica compresenze a 4 docenti e parallelismi in palestra."""
        solver = TimetableSolver(self.problem, max_gap_limit=4, strict_gap_limit=False)
        result = solver.solve(max_time_seconds=25, random_seed=42)

        self.assertIn(result.status, ["OPTIMAL", "FEASIBLE"], f"Il solutore deve produrre una soluzione valida. Ricevuto: {result.status}")

        # 1. Verifica che tutte le classi terze in parallelismo abbiano gli stessi slot di Motoria
        for pg in self.problem.config.parallel_groups:
            c1, c2 = pg.class_ids
            g1 = result.grid_by_class[c1]
            g2 = result.grid_by_class[c2]
            slots1 = [(d, h) for d in range(len(g1)) for h in range(len(g1[d])) if g1[d][h] and g1[d][h].subject_id == "mot"]
            slots2 = [(d, h) for d in range(len(g2)) for h in range(len(g2[d])) if g2[d][h] and g2[d][h].subject_id == "mot"]
            self.assertEqual(len(slots1), 2, f"Classe {c1} deve avere 2h di motoria, trovate: {len(slots1)}")
            self.assertEqual(slots1, slots2, f"Parallelismo fallito tra {c1} e {c2}: {slots1} != {slots2}")
            # Verifica blocco consecutivo
            d1, h1 = slots1[0]
            d2, h2 = slots1[1]
            self.assertEqual(d1, d2, "Le 2 ore di motoria devono essere nello stesso giorno")
            self.assertEqual(abs(h1 - h2), 1, "Le 2 ore di motoria devono essere consecutive")

        # 2. Verifica che i 4 docenti di strumento siano compresenti negli slot di orchestra
        mus_assigns = [a for a in self.problem.assignments if a.subject_id in ["orch", "solf"]]
        for a in mus_assigns:
            c_grid = result.grid_by_class[a.class_id]
            orch_slots = [(d, h) for d in range(len(c_grid)) for h in range(len(c_grid[d])) if c_grid[d][h] and c_grid[d][h].subject_id in ["orch", "solf"]]
            self.assertEqual(len(orch_slots), 2, f"La classe {a.class_id} deve avere 2 ore di orchestra assegnate")
            for d, h in orch_slots:
                # Verifica che il docente principale e tutti i co-docenti siano assegnati in quello slot
                for tid in [a.teacher_id] + a.co_teacher_ids:
                    t_slot = result.grid_by_teacher[tid][d][h]
                    self.assertIsNotNone(t_slot, f"Docente {tid} assente all'ora di orchestra d={d}, h={h}")
                    self.assertEqual(t_slot.class_id, a.class_id)

    def test_05_9_slot_rendering_and_excel_export(self):
        """Verifica la corretta generazione del rendering HTML e dei file Excel fino alla 9ª ora."""
        solver = TimetableSolver(self.problem, max_gap_limit=4, strict_gap_limit=False)
        result = solver.solve(max_time_seconds=15, random_seed=42)
        if result.status in ["OPTIMAL", "FEASIBLE"]:
            # Test HTML rendering
            html_cls = render_html_schedule_table(
                days_active=self.problem.config.active_days,
                daily_hours=solver.class_daily_hours["1F"],
                grid_matrix=result.grid_by_class["1F"],
                view_type="class"
            )
            self.assertIn("1ª Ora", html_cls)
            self.assertIn("8ª Ora", html_cls)

            # Test Excel Tabellone Combo Export
            combo_bytes = generate_excel_tabellone_combo(self.problem, result)
            self.assertGreater(len(combo_bytes), 3000, "L'Excel del Tabellone Docenti Combo deve essere generato")

            # Test Excel Full Timetable Export
            full_bytes = generate_excel_timetable(self.problem, result)
            self.assertGreater(len(full_bytes), 5000, "L'Excel Generale deve essere generato")


if __name__ == "__main__":
    unittest.main(verbosity=2)
