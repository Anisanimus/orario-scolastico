"""
Motore di Risoluzione per l'Orario Scolastico basato su Google OR-Tools (CP-SAT).
Supporta modello Tradizionale e modello DADA con gestione completa di desiderata avanzati:
giorno libero, entrare tardi, uscire presto, slot puntuali sconsigliati, ore doppie e riduzione buchi.
"""
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from dataclasses import dataclass, field
from ortools.sat.python import cp_model
from models import TimetableProblem, DAYS_OF_WEEK, TeachingAssignment, Teacher, Classroom

@dataclass
class LessonSlotInfo:
    assignment_id: str
    class_id: str
    class_name: str
    teacher_id: str
    teacher_name: str
    subject_id: str
    subject_name: str
    subject_color: str
    room_id: Optional[str] = None
    room_name: Optional[str] = None
    is_double: bool = False
    co_teachers: List[str] = field(default_factory=list) # Docenti in compresenza su questa cattedra
    parallel_classes: List[str] = field(default_factory=list) # Altre classi in contemporanea / classi aperte
    parallel_teachers: List[str] = field(default_factory=list) # Altri docenti in contemporanea
    is_compresenza: bool = False # True se presente compresenza o classi aperte
    compresenza_text: str = "" # Descrizione chiara (es. "Compresenza con 1D (Prof. Vitale)")

@dataclass
class TimetableResult:
    status: str  # "OPTIMAL", "FEASIBLE", "INFEASIBLE", "NOT_SOLVED"
    solve_time: float = 0.0
    objective_value: float = 0.0
    
    # [class_id][day_idx][hour_idx] -> LessonSlotInfo or None
    grid_by_class: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)
    
    # [teacher_id][day_idx][hour_idx] -> LessonSlotInfo or None
    grid_by_teacher: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)

    # [room_id][day_idx][hour_idx] -> LessonSlotInfo or None (Griglia occupazione Aule)
    grid_by_room: Dict[str, List[List[Optional[LessonSlotInfo]]]] = field(default_factory=dict)
    
    # Statistiche Desiderata
    total_gap_hours: int = 0
    gaps_by_teacher: Dict[str, int] = field(default_factory=dict)
    free_days_satisfied_first: int = 0
    free_days_total_first: int = 0
    free_days_satisfied_second: int = 0
    free_days_total_second: int = 0
    double_hours_satisfied: int = 0
    double_hours_total: int = 0
    double_hours_by_subject: Dict[str, Dict[str, Any]] = field(default_factory=dict) # Dettaglio per materia flaggata
    triple_hours_satisfied: int = 0
    triple_hours_total: int = 0
    triple_hours_pct: int = 100
    
    # Desiderata Avanzati
    soft_slots_satisfied: int = 0
    soft_slots_total: int = 0
    late_entry_satisfied: int = 0
    late_entry_total: int = 0
    early_exit_satisfied: int = 0
    early_exit_total: int = 0
    
    # Report Dettagliato per Docente ("Chi ho soddisfatto e chi no")
    teacher_reports: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    global_satisfaction_score: float = 100.0
    
    log_messages: List[str] = field(default_factory=list)

def diagnose_problem_feasibility(problem: TimetableProblem) -> List[str]:
    """Analizza a fondo la configurazione e restituisce una lista dettagliata e specifica di eventuali incongruenze, conflitti o colli di bottiglia nei dati."""
    issues = []
    tot_slots = problem.config.total_weekly_slots
    num_days = problem.config.num_days
    daily_hours = problem.config.daily_hours[:num_days]
    
    # 1. Controllo Monte Ore Classi (Target specifico 30h, 32h Musicale, 36h Prolungato o totale slot scuola)
    for c_id, c in problem.classes.items():
        target_class_h = getattr(c, "weekly_hours_target", tot_slots) or tot_slots
        c_h = sum(a.hours_per_week for a in problem.assignments if a.class_id == c_id)
        if c_h != target_class_h:
            diff = c_h - target_class_h
            if diff > 0:
                issues.append(f"❌ **Classe {c.name}**: ha **{c_h} ore settimanali** (+{diff}h in eccesso rispetto alle {target_class_h}h previste per il suo indirizzo).")
            else:
                issues.append(f"❌ **Classe {c.name}**: ha **{c_h} ore settimanali** (mancano {-diff}h per raggiungere le {target_class_h}h previste per il suo indirizzo).")

    # 2. Controllo Part-Time, Disponibilità e Indisponibilità Docenti
    for t_id, t in problem.teachers.items():
        t_assignments = [a for a in problem.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
        t_h = sum(a.hours_per_week for a in t_assignments)
        unavail = len(getattr(t, "unavailable_slots", []))
        free_slots = tot_slots - unavail
        
        # A. Cattedra superiore alle ore feriali residue disponibili
        if t_h > free_slots:
            issues.append(f"❌ **Docente {t.name}**: cattedra da **{t_h} ore** ma con **{unavail} ore di indisponibilità tassativa** (restano solo {free_slots} ore utili su {tot_slots}h).")

        # B. Incompatibilità Part-Time su Giorni Massimi e Carico Giornaliero
        if t.is_part_time and t.max_working_days is not None:
            max_d = max(1, t.max_working_days)
            max_h_day = getattr(t, "max_daily_hours", 5) or 5
            max_pt_cap = max_d * max_h_day
            if t_h > max_pt_cap:
                min_days_needed = (t_h + max_h_day - 1) // max_h_day
                issues.append(f"❌ **Docente Part-Time {t.name}**: cattedra da **{t_h}h** assegnata su max **{max_d} giorni** (capienza max {max_pt_cap}h con max {max_h_day}h/giorno). Servono almeno **{min_days_needed} giorni** di presenza a scuola.")

            # Controllo giorni liberi part-time vs slot obbligatori
            f_days_names = getattr(t, "free_days", [])
            for fd_name in f_days_names:
                if fd_name in DAYS_OF_WEEK:
                    fd_idx = DAYS_OF_WEEK.index(fd_name)
                    # Verifica se ha lezioni fissate o slot di presenza tassativa nel giorno libero
                    req_in_fd = [s for s in getattr(t, "required_slots", []) if s[0] == fd_idx]
                    if req_in_fd:
                        issues.append(f"❌ **Docente Part-Time {t.name}**: impostati **{len(req_in_fd)} slot di presenza obbligatoria** il **{fd_name}**, che è indicato come Giorno Libero.")

        # C. Controllo slot obbligatori (Includi) e incompatibilità con Escludi
        req_slots = getattr(t, "required_slots", [])
        if len(req_slots) > t_h:
            issues.append(f"❌ **Docente {t.name}**: impostati **{len(req_slots)} slot di presenza obbligatoria** ma la cattedra è di sole **{t_h} ore**.")
        
        for r_s in req_slots:
            if r_s in getattr(t, "unavailable_slots", []):
                d_name = DAYS_OF_WEEK[r_s[0]] if r_s[0] < len(DAYS_OF_WEEK) else f"Giorno {r_s[0]+1}"
                issues.append(f"❌ **Docente {t.name}**: conflitto nello slot **{d_name} ({r_s[1]+1}ª ora)** impostato contemporaneamente sia come 'Escludi' che come 'Includi tassativo'.")

    # 3. Controllo Conflitti su Lezioni Prefissate / Bloccate (Pinned Slots)
    pinned_by_slot: Dict[Tuple[int, int], List[TeachingAssignment]] = {}
    pinned_by_teacher_slot: Dict[Tuple[str, int, int], List[TeachingAssignment]] = {}
    pinned_by_class_slot: Dict[Tuple[str, int, int], List[TeachingAssignment]] = {}
    
    for a in problem.assignments:
        for p_slot in getattr(a, "pinned_slots", []):
            if len(p_slot) == 2:
                d, h = p_slot[0], p_slot[1]
                slot_key = (d, h)
                pinned_by_slot.setdefault(slot_key, []).append(a)
                pinned_by_teacher_slot.setdefault((a.teacher_id, d, h), []).append(a)
                pinned_by_class_slot.setdefault((a.class_id, d, h), []).append(a)
                
                # Conflitto con indisponibilità docente
                t_obj = problem.teachers.get(a.teacher_id)
                if t_obj and [d, h] in getattr(t_obj, "unavailable_slots", []):
                    d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
                    issues.append(f"❌ **Conflitto Lezione Bloccata**: la lezione di **{t_obj.name}** per la classe **{a.class_id}** è bloccata il **{d_name} alla {h+1}ª ora**, ma il docente è contrassegnato come Indisponibile in quell'ora.")

    # Conflitto: stesso docente bloccato su 2 classi diverse nella stessa ora
    for (t_id, d, h), a_list in pinned_by_teacher_slot.items():
        if len(a_list) > 1:
            t_name = problem.teachers[t_id].name if t_id in problem.teachers else t_id
            d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
            c_names = ", ".join(problem.classes[a_item.class_id].name if a_item.class_id in problem.classes else a_item.class_id for a_item in a_list)
            issues.append(f"❌ **Conflitto Sovrapposizione Docente**: il docente **{t_name}** ha **{len(a_list)} lezioni bloccate** contemporaneamente il **{d_name} alla {h+1}ª ora** sulle classi: {c_names}.")

    # Conflitto: stessa classe con 2 materie diverse bloccate nella stessa ora
    for (c_id, d, h), a_list in pinned_by_class_slot.items():
        if len(a_list) > 1:
            c_name = problem.classes[c_id].name if c_id in problem.classes else c_id
            d_name = DAYS_OF_WEEK[d] if d < len(DAYS_OF_WEEK) else f"Giorno {d+1}"
            issues.append(f"❌ **Conflitto Sovrapposizione Classe**: la classe **{c_name}** ha **{len(a_list)} materie bloccate** contemporaneamente il **{d_name} alla {h+1}ª ora** ({s_names}).")

    # 4. Controllo Capienza Aule e Spazi (DADA & Tradizionale)
    is_dada = bool(getattr(problem.config, "is_dada", False))
    room_group_req: Dict[Tuple[str, ...], List[TeachingAssignment]] = {}
    
    for a in problem.assignments:
        comp = []
        if a.preferred_room_id and a.preferred_room_id in problem.rooms:
            comp = [a.preferred_room_id]
        else:
            if is_dada:
                matching = [
                    r_id for r_id, r in problem.rooms.items()
                    if a.subject_id in r.subject_ids
                    and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                ]
                if not matching:
                    matching = [r_id for r_id, r in problem.rooms.items() if a.subject_id in r.subject_ids]
                comp = matching
            else:
                matching_special = [
                    r_id for r_id, r in problem.rooms.items()
                    if r.is_special_lab and a.subject_id in r.subject_ids
                    and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                ]
                if not matching_special:
                    matching_special = [
                        r_id for r_id, r in problem.rooms.items()
                        if r.is_special_lab and a.subject_id in r.subject_ids
                    ]
                comp = matching_special
        if comp:
            comp_tuple = tuple(sorted(comp))
            room_group_req.setdefault(comp_tuple, []).append(a)

    for comp_tuple, a_list in room_group_req.items():
        req_h = sum(a.hours_per_week for a in a_list)
        total_cap_h = sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms) * tot_slots
        if req_h > total_cap_h:
            names = ", ".join(problem.rooms[r_id].name for r_id in comp_tuple if r_id in problem.rooms)
            issues.append(
                f"❌ **Spazi/Laboratori ({names})**: richieste **{req_h} ore** settimanali ma la capienza massima disponibile è di **{total_cap_h} ore**.\n"
                f"   *(💡 Suggerimento: valuta se lavorare a **classi aperte** per queste classi oppure dedicare un **secondo spazio** a questa disciplina)*"
            )

    # 5. Controllo compatibilità accoppiamento a 2 ore
    for a in problem.assignments:
        if a.force_double_hours and a.hours_per_week == 1:
            issues.append(f"⚠️ **Cattedra {a.id} ({a.subject_id})**: forzata a blocco da 2h ma ha solo 1 ora settimanale.")

    # 6. Controllo Gruppi di Classi Aperte & Parallelismi Didattici
    for grp in getattr(problem.config, "parallel_groups", []):
        if not getattr(grp, "is_active", True):
            continue
        g_assigns = []
        for cid in grp.class_ids:
            matching = [a for a in problem.assignments if a.class_id == cid and a.subject_id == grp.subject_id]
            if matching:
                g_assigns.append(matching[0])
            else:
                c_name = problem.classes[cid].name if cid in problem.classes else cid
                s_name = problem.subjects[grp.subject_id].name if grp.subject_id in problem.subjects else grp.subject_id
                issues.append(f"❌ **Classi Aperte '{grp.name}'**: la classe **{c_name}** non ha cattedre assegnate per la materia **{s_name}**.")
        
        if len(g_assigns) >= 2:
            # Controllo docenti
            t_ids = [a.teacher_id for a in g_assigns]
            if len(set(t_ids)) < len(t_ids):
                # Se un docente è presente su più classi del gruppo, attiva automaticamente la modalità lezione accorpata / congiunta
                grp.is_same_teacher_merged = True

            # Controllo capienza spazio condiviso se impostato
            if getattr(grp, "room_id", None) and grp.room_id in problem.rooms:
                r_obj = problem.rooms[grp.room_id]
                if r_obj.capacity < len(grp.class_ids):
                    issues.append(
                        f"⚠️ **Capienza Spazio Classi Aperte '{grp.name}'**: l'aula/palestra **{r_obj.name}** ha capienza {r_obj.capacity}, ma il gruppo comprende {len(grp.class_ids)} classi in contemporanea. La capienza dell'aula deve essere portata ad almeno {len(grp.class_ids)}."
                    )

    return issues

def get_room_bottlenecks(problem: TimetableProblem) -> List[Dict[str, Any]]:
    """Identifica con precisione i colli di bottiglia di aule e laboratori sovraffollati."""
    tot_slots = problem.config.total_weekly_slots
    bottlenecks = []
    is_dada = bool(getattr(problem.config, "is_dada", False))
    
    room_group_req: Dict[Tuple[str, ...], List[TeachingAssignment]] = {}
    for a in problem.assignments:
        comp = []
        if a.preferred_room_id and a.preferred_room_id in problem.rooms:
            comp = [a.preferred_room_id]
        else:
            if is_dada:
                matching = [
                    r_id for r_id, r in problem.rooms.items()
                    if a.subject_id in r.subject_ids
                    and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                ]
                if not matching:
                    matching = [r_id for r_id, r in problem.rooms.items() if a.subject_id in r.subject_ids]
                comp = matching
            else:
                matching_special = [
                    r_id for r_id, r in problem.rooms.items()
                    if r.is_special_lab and a.subject_id in r.subject_ids
                    and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                ]
                if not matching_special:
                    matching_special = [
                        r_id for r_id, r in problem.rooms.items()
                        if r.is_special_lab and a.subject_id in r.subject_ids
                    ]
                comp = matching_special
        if comp:
            comp_tuple = tuple(sorted(comp))
            room_group_req.setdefault(comp_tuple, []).append(a)

    for comp_tuple, a_list in room_group_req.items():
        req_h = sum(a.hours_per_week for a in a_list)
        total_cap_h = sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms) * tot_slots
        if req_h > total_cap_h:
            names = ", ".join(problem.rooms[r_id].name for r_id in comp_tuple if r_id in problem.rooms)
            bottlenecks.append({
                "type": "teacher_room" if len(comp_tuple) == 1 else "subject_lab",
                "room_ids": list(comp_tuple),
                "primary_room_id": comp_tuple[0],
                "room_name": names,
                "current_capacity": sum(problem.rooms[r_id].capacity for r_id in comp_tuple if r_id in problem.rooms),
                "required_hours": req_h,
                "available_hours": total_cap_h,
                "excess_hours": req_h - total_cap_h,
                "teacher_ids": list(set(a.teacher_id for a in a_list)),
                "subject_ids": list(set(a.subject_id for a in a_list)),
                "class_ids": list(set(a.class_id for a in a_list)),
                "assignments": a_list
            })
    return bottlenecks

class TimetableSolver:
    def __init__(self, problem: TimetableProblem, max_gap_limit: int = 6, strict_gap_limit: bool = False):
        self.problem = problem
        self.cfg = problem.config
        self.num_days = self.cfg.num_days
        self.base_daily_hours = self.cfg.daily_hours[:self.num_days]
        self.max_gap_limit = max_gap_limit
        self.strict_gap_limit = strict_gap_limit
        self.model = cp_model.CpModel()
        
        # Calcolo slot giornalieri effettivi per ciascuna classe (con rientri pomeridiani: +1h o +2h)
        self.class_daily_hours: Dict[str, List[int]] = {}
        for c_id, c in problem.classes.items():
            c_dh = list(self.base_daily_hours)
            aft_days = getattr(c, "afternoon_days", []) or []
            target_h = getattr(c, "weekly_hours_target", sum(c_dh)) or sum(c_dh)
            diff_h = target_h - sum(c_dh)
            
            if diff_h > 0 and aft_days:
                # Distribuisci le ore pomeridiane aggiuntive sui giorni di rientro
                extra_per_day = diff_h // len(aft_days)
                rem_extra = diff_h % len(aft_days)
                for idx_d, d_name in enumerate(DAYS_OF_WEEK[:self.num_days]):
                    if d_name in aft_days:
                        c_dh[idx_d] += extra_per_day + (1 if rem_extra > 0 else 0)
                        rem_extra = max(0, rem_extra - 1)
            elif diff_h > 0:
                # Se non specificato, aggiungi all'inizio settimana
                for idx_d in range(min(diff_h, self.num_days)):
                    c_dh[idx_d] += 1
            self.class_daily_hours[c_id] = c_dh

        # Ore massime per giorno della scuola (compresi i pomeriggi)
        self.daily_hours = [
            max([self.class_daily_hours[c_id][d] for c_id in problem.classes] + [self.base_daily_hours[d]])
            if problem.classes else self.base_daily_hours[d]
            for d in range(self.num_days)
        ]
        
        # Variabili di decisione: (assignment_id, d, h) -> BoolVar
        self.x = {}
        
        # Variabili assegnazione aule: (assignment_id, room_id, d, h) -> BoolVar
        self.y_room = {}
        
        # Variabili presenza docente: (teacher_id, d, h) -> BoolVar
        self.t_active = {}
        self.t_day_active = {}
        self.t_gap = {}
        self.all_pair_vars = []
        
        # Mappatura cattedra -> lista aule compatibili
        self.assignment_compatible_rooms: Dict[str, List[str]] = {}

    def _get_day_index(self, day_name: Optional[str]) -> Optional[int]:
        if not day_name:
            return None
        name_clean = day_name.strip().capitalize()
        for idx, d in enumerate(DAYS_OF_WEEK):
            if d.lower() == name_clean.lower():
                return idx
        return None

    def _determine_compatible_rooms(self):
        """Associa a ciascuna cattedra l'insieme ordinato di aule compatibili rispettando priorità e assegnazione docenti al 100%."""
        prob = self.problem
        is_dada = prob.config.is_dada

        for a in prob.assignments:
            comp_rooms = []
            subj = prob.subjects.get(a.subject_id)
            
            # 1. Aula specifica preferita o obbligatoria per questa cattedra
            if a.preferred_room_id and a.preferred_room_id in prob.rooms:
                comp_rooms = [a.preferred_room_id]
            else:
                # 2. Assegnazione aula a questo specifico docente (100% esaudita prioritariamente)
                teacher_rooms = [
                    r_id for r_id, r in prob.rooms.items()
                    if a.teacher_id in getattr(r, "teacher_ids", [])
                    and (not r.subject_ids or a.subject_id in r.subject_ids)
                ]
                if teacher_rooms:
                    # Ordina per priorità aula (1 = Massima priorità / Principale, 2 = Secondaria, 3 = Riserva)
                    teacher_rooms.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                    comp_rooms = teacher_rooms
                elif subj and subj.special_room_id and subj.special_room_id in prob.rooms:
                    comp_rooms = [subj.special_room_id]
                else:
                    # 3. Matching per materia:
                    # Se DADA: match su tutte le aule dedicate alla disciplina (ordinate per priorità)
                    # Se Tradizionale: match solo sui laboratori e aule speciali condivise (Palestre, Lab Arte, Musica, Tec)
                    if is_dada:
                        matching = [
                            r_id for r_id, r in prob.rooms.items()
                            if a.subject_id in r.subject_ids
                            and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                        ]
                        if not matching:
                            # Fallback 1: qualsiasi aula della stessa materia
                            matching = [r_id for r_id, r in prob.rooms.items() if a.subject_id in r.subject_ids]
                        if matching:
                            matching.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                            comp_rooms = matching
                        else:
                            generic = [
                                r_id for r_id, r in prob.rooms.items()
                                if not r.is_special_lab and len(r.subject_ids) == 0
                            ]
                            if generic:
                                generic.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                                comp_rooms = generic
                    else:
                        matching_special = [
                            r_id for r_id, r in prob.rooms.items()
                            if r.is_special_lab and a.subject_id in r.subject_ids
                            and (not getattr(r, "teacher_ids", []) or a.teacher_id in getattr(r, "teacher_ids", []))
                        ]
                        if not matching_special:
                            matching_special = [
                                r_id for r_id, r in prob.rooms.items()
                                if r.is_special_lab and a.subject_id in r.subject_ids
                            ]
                        if matching_special:
                            matching_special.sort(key=lambda r_id: getattr(prob.rooms[r_id], "priority", 1))
                            comp_rooms = matching_special

            self.assignment_compatible_rooms[a.id] = comp_rooms

    def build_model(self, skip_penalties: bool = False):
        m = self.model
        prob = self.problem
        num_days = self.num_days
        daily_hours = self.daily_hours

        self._determine_compatible_rooms()
        self.all_pair_vars = []
        is_dada_strict_pairs = bool(getattr(prob.config, "is_dada", False) and getattr(prob.config, "dada_strict_even_pairs", False))

        # 1. Creazione variabili principali X[assignment, d, h]
        for a in prob.assignments:
            for d in range(num_days):
                for h in range(daily_hours[d]):
                    var_name = f"x_{a.id}_d{d}_h{h}"
                    self.x[a.id, d, h] = m.NewBoolVar(var_name)

        # 2. VINCOLO RIGIDO: Monte ore settimanale esatto per ciascuna cattedra
        for a in prob.assignments:
            assigned_slots = [self.x[a.id, d, h] for d in range(num_days) for h in range(daily_hours[d])]
            m.Add(sum(assigned_slots) == a.hours_per_week)

            # Fascia oraria preferita (morning_only: ore 1-4 antimeridiane, afternoon_only: ore >= 5 pomeridiane)
            pref_tod = getattr(a, "preferred_time_of_day", "any")
            if pref_tod == "morning_only":
                for d in range(num_days):
                    for h in range(4, daily_hours[d]): # Dalla 5ª ora in poi è vietato
                        m.Add(self.x[a.id, d, h] == 0)
            elif pref_tod == "afternoon_only":
                for d in range(num_days):
                    for h in range(min(4, daily_hours[d])): # Nelle prime 4 ore è vietato
                        m.Add(self.x[a.id, d, h] == 0)

        # 3. VINCOLO RIGIDO: Una classe può avere al massimo 1 lezione per ora (e solo nelle sue ore giornaliere previste)
        for class_id, class_obj in prob.classes.items():
            class_assignments = [a for a in prob.assignments if a.class_id == class_id]
            c_dh = self.class_daily_hours.get(class_id, self.base_daily_hours)
            for d in range(num_days):
                max_h_for_class_today = c_dh[d] if d < len(c_dh) else daily_hours[d]
                for h in range(daily_hours[d]):
                    slots = [self.x[a.id, d, h] for a in class_assignments]
                    if h < max_h_for_class_today:
                        m.Add(sum(slots) <= 1)
                    else:
                        # Fuori dall'orario di questa classe in questo giorno -> nessuna lezione
                        m.Add(sum(slots) == 0)

        # 4. VINCOLO RIGIDO: Classi Aperte & Parallelismi Didattici (Sincronizzazione Oraria Perfetta)
        active_parallel_groups = [g for g in getattr(prob.config, "parallel_groups", []) if getattr(g, "is_active", True)]
        self.parallel_group_slot_vars = {}

        for g_idx, grp in enumerate(active_parallel_groups):
            group_assigns = []
            for cid in grp.class_ids:
                matching_a = [a for a in prob.assignments if a.class_id == cid and a.subject_id == grp.subject_id]
                if matching_a:
                    group_assigns.append(matching_a[0])
            
            if len(group_assigns) < 2:
                continue
                
            lead_a = group_assigns[0]
            follower_assigns = group_assigns[1:]
            p_hours = min(grp.parallel_hours, lead_a.hours_per_week)
            
            if p_hours >= lead_a.hours_per_week:
                # Sincronizzazione totale per tutte le ore della materia
                for other_a in follower_assigns:
                    for d in range(num_days):
                        for h in range(daily_hours[d]):
                            m.Add(self.x[lead_a.id, d, h] == self.x[other_a.id, d, h])
                self.parallel_group_slot_vars[grp.id] = None
            else:
                # Sincronizzazione parziale (es. 2h in parallelo su 5h di materia)
                p_slot_vars = {}
                for d in range(num_days):
                    for h in range(daily_hours[d]):
                        p_var = m.NewBoolVar(f"p_slot_{grp.id}_{g_idx}_d{d}_h{h}")
                        p_slot_vars[d, h] = p_var
                        for a_obj in group_assigns:
                            m.Add(self.x[a_obj.id, d, h] >= p_var)
                
                m.Add(sum(p_slot_vars.values()) == p_hours)
                self.parallel_group_slot_vars[grp.id] = p_slot_vars
                
                if grp.force_consecutive_block and p_hours == 2:
                    pair_vars = []
                    for d in range(num_days):
                        allowed_starts = [h for h in range(0, daily_hours[d] - 1, 2)] if is_dada_strict_pairs else [h for h in range(daily_hours[d] - 1)]
                        for h in allowed_starts:
                            p_curr = p_slot_vars[d, h]
                            p_next = p_slot_vars[d, h+1]
                            pv = m.NewBoolVar(f"p_pair_{grp.id}_{g_idx}_d{d}_h{h}")
                            m.Add(pv <= p_curr)
                            m.Add(pv <= p_next)
                            m.Add(pv >= p_curr + p_next - 1)
                            pair_vars.append(pv)
                            self.all_pair_vars.append(pv)
                    if pair_vars:
                        m.Add(sum(pair_vars) == 1)

        # 5. Variabili e VINCOLO RIGIDO: Docenti (No sovrapposizioni e carichi giornalieri)
        # Supporta nativamente:
        # - Compresenze multiple fino a 4 docenti (Orchestra, Solfeggio, Prolungato)
        # - Minimo 2 ore al giorno (mai 1 ora singola se presente)
        # - Massimo 5 ore in un giorno
        # - Fino a 4 ore consecutive di fila
        # - Classi aperte/accorpate con docente unico
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in getattr(a, "co_teacher_ids", [])]
            t_total_h = sum(a.hours_per_week for a in t_assignments)
            
            # Parametri di servizio del docente
            max_daily = getattr(teacher, "max_daily_hours", 5) or 5
            max_consec = getattr(teacher, "max_consecutive_hours", 4) or 4
            min_daily = getattr(teacher, "min_daily_hours", 2) or 2
            eff_min_daily = min(min_daily, t_total_h) if t_total_h > 0 else 0

            # Raggruppa le cattedre del docente appartenenti allo stesso gruppo parallelo
            t_pg_groups = []
            assigned_in_pg = set()
            for grp in active_parallel_groups:
                g_a_ids = [a.id for a in t_assignments if a.class_id in grp.class_ids and a.subject_id == grp.subject_id]
                if len(g_a_ids) >= 1:
                    t_pg_groups.append((grp, g_a_ids))
                    assigned_in_pg.update(g_a_ids)

            stand_alone_a_ids = [a.id for a in t_assignments if a.id not in assigned_in_pg]
            
            for d in range(num_days):
                H = daily_hours[d]
                daily_active_terms = []

                for h in range(H):
                    slot_terms = [self.x[a_id, d, h] for a_id in stand_alone_a_ids]
                    for grp, g_a_ids in t_pg_groups:
                        if len(g_a_ids) == 1:
                            slot_terms.append(self.x[g_a_ids[0], d, h])
                        else:
                            p_vars_dict = self.parallel_group_slot_vars.get(grp.id)
                            if p_vars_dict and (d, h) in p_vars_dict:
                                p_v = p_vars_dict[d, h]
                                slot_terms.append(sum(self.x[aid, d, h] for aid in g_a_ids) - (len(g_a_ids) - 1) * p_v)
                            else:
                                slot_terms.append(self.x[g_a_ids[0], d, h])
                    if slot_terms:
                        m.Add(sum(slot_terms) <= 1)
                        t_slot_var = m.NewBoolVar(f"t_work_{t_id}_d{d}_h{h}")
                        m.Add(t_slot_var == sum(slot_terms))
                        daily_active_terms.append(t_slot_var)
                    else:
                        daily_active_terms.append(0)
                
                day_act = m.NewBoolVar(f"t_day_active_{t_id}_d{d}")
                self.t_day_active[t_id, d] = day_act
                if t_total_h > 0:
                    # Regola 1: Minimo 2 ore al giorno (se presente, tranne per docenti di strumento con cattedre parziali o slot fissati)
                    is_instrument_or_special = any(a.subject_id in ["orch", "solf"] for a in t_assignments) or (t_total_h < 10)
                    if eff_min_daily > 0 and not is_instrument_or_special:
                        m.Add(sum(daily_active_terms) >= eff_min_daily * day_act)
                    else:
                        m.Add(sum(daily_active_terms) >= 1 * day_act)

                    # Regola 2: Massimo ore al giorno (default 5 ore)
                    m.Add(sum(daily_active_terms) <= max_daily * day_act)

                    # Regola 3: Fino a 4 ore di fila (mai 5 ore consecutive continue)
                    if max_consec < H:
                        w_size = max_consec + 1
                        for h in range(H - max_consec):
                            m.Add(sum(daily_active_terms[h + k] for k in range(w_size)) <= max_consec)
                else:
                    m.Add(day_act == 0)

            if num_days == 6 and not teacher.is_part_time:
                m.Add(sum(self.t_day_active[t_id, d] for d in range(6)) <= 5)

        # 6. VINCOLO RIGIDO: Indisponibilità assoluta (Escludi) e Presenza Tassativa (Includi) dei Docenti
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id]
            # A. Escludi (Indisponibilità assoluta - NO Lezione)
            for slot in getattr(teacher, "unavailable_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(sum(self.x[a.id, d, h] for a in t_assignments) == 0)
            
            # B. Includi (Presenza Tassativa - DEVE avere Lezione)
            for slot in getattr(teacher, "required_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(sum(self.x[a.id, d, h] for a in t_assignments) == 1)

        # 7. VINCOLO RIGIDO: Pre-fissaggio Tassativo di Lezioni Specifiche (Classe + Materia nello Slot)
        for a in prob.assignments:
            for slot in getattr(a, "pinned_slots", []):
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        m.Add(self.x[a.id, d, h] == 1)

        # 8. VINCOLO RIGIDO: Capienza Massima Aule Speciali & Laboratori (Palestre, Teatri, Lab Condivisi)
        # Raggruppa SOLO le cattedre che competono per spazi speciali condivisi a capienza limitata
        room_group_map: Dict[Tuple[str, ...], List[str]] = {}
        for a in prob.assignments:
            comp = tuple(sorted(self.assignment_compatible_rooms.get(a.id, [])))
            if comp and any(r_id in prob.rooms and prob.rooms[r_id].is_special_lab for r_id in comp):
                room_group_map.setdefault(comp, []).append(a.id)

        for comp_rooms_tuple, assign_ids in room_group_map.items():
            rooms_in_grp = [prob.rooms[r_id] for r_id in comp_rooms_tuple if r_id in prob.rooms]
            total_cap = sum(r.capacity for r in rooms_in_grp)
            
            # Per ciascun gruppo parallelo che usa questo spazio condiviso, le sue classi occupano 1 unità di capienza congiunta
            pg_in_room = []
            assigns_in_room_pg = set()
            for grp in active_parallel_groups:
                g_a_ids = [aid for aid in assign_ids if any(a.id == aid and a.class_id in grp.class_ids and a.subject_id == grp.subject_id for a in prob.assignments)]
                if len(g_a_ids) >= 2:
                    pg_in_room.append((grp, g_a_ids))
                    assigns_in_room_pg.update(g_a_ids)

            stand_alone_room_assigns = [aid for aid in assign_ids if aid not in assigns_in_room_pg]

            for d in range(num_days):
                for h in range(daily_hours[d]):
                    slot_room_terms = [self.x[a_id, d, h] for a_id in stand_alone_room_assigns]
                    for grp, g_a_ids in pg_in_room:
                        p_vars_dict = self.parallel_group_slot_vars.get(grp.id)
                        if p_vars_dict and (d, h) in p_vars_dict:
                            p_v = p_vars_dict[d, h]
                            slot_room_terms.append(sum(self.x[aid, d, h] for aid in g_a_ids) - (len(g_a_ids) - 1) * p_v)
                        else:
                            slot_room_terms.append(self.x[g_a_ids[0], d, h])
                    m.Add(sum(slot_room_terms) <= total_cap)

        # 9. VINCOLO DIDATTICO RIGIDO: Max ore al giorno per materia in una classe
        for a in prob.assignments:
            f_dbl = a.force_double_hours or (hasattr(prob.config, "subject_block_preferences") and prob.config.subject_block_preferences.get(a.subject_id, False))
            is_in_2h_parallel = any(
                grp.is_active and a.class_id in grp.class_ids and a.subject_id == grp.subject_id and (grp.force_consecutive_block or grp.parallel_hours >= 2)
                for grp in active_parallel_groups
            )
            if not f_dbl and not is_in_2h_parallel:
                eff_max_h = min(getattr(a, "max_daily_hours", 2) or 2, 2)
                for d in range(num_days):
                    daily_slots = [self.x[a.id, d, h] for h in range(daily_hours[d])]
                    m.Add(sum(daily_slots) <= eff_max_h)
            else:
                eff_max_h = 2
                for d in range(num_days):
                    daily_slots = [self.x[a.id, d, h] for h in range(daily_hours[d])]
                    m.Add(sum(daily_slots) <= eff_max_h)

        # -------------------------------------------------------------
        # MODELLAZIONE SOFT CONSTRAINTS / DESIDERATA & FUNZIONE OBIETTIVO
        # -------------------------------------------------------------
        penalties = []

        criteria = getattr(prob.config, "optimization_criteria", None) or OptimizationCriteria()

        # B. DESIDERATA: Giorno Libero Docenti (Settimana corta vs lunga) & Vincolo Giorni Part-Time
        for t_id, teacher in prob.teachers.items():
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            t_total_h = sum(a.hours_per_week for a in t_assignments)
            
            # VINCOLO RIGIDO PART-TIME: Massimo N Giorni di presenza a scuola
            if teacher.is_part_time and teacher.max_working_days is not None:
                eff_max_d = max(teacher.max_daily_hours, 1)
                min_days_needed = (t_total_h + eff_max_d - 1) // eff_max_d if eff_max_d > 0 else 1
                allowed_max_days = max(teacher.max_working_days, min_days_needed)
                allowed_max_days = min(allowed_max_days, num_days)
                
                # Vincolo rigido: non può venire a scuola più giorni di quelli concordati
                m.Add(sum(self.t_day_active[t_id, d] for d in range(num_days)) <= allowed_max_days)

            can_have_free_day = (num_days == 6) or teacher.is_part_time or (t_total_h <= 14)
            
            if can_have_free_day and not skip_penalties:
                target_free_days = getattr(teacher, "free_days", [])
                if not target_free_days:
                    target_free_days = []
                    if teacher.free_day_1: target_free_days.append(teacher.free_day_1)
                    if teacher.free_day_2: target_free_days.append(teacher.free_day_2)

                w_base = max(getattr(criteria, "weight_free_day", 800), 800)
                for p_idx, fd_name in enumerate(target_free_days):
                    fd_idx = self._get_day_index(fd_name)
                    if fd_idx is not None and fd_idx < num_days:
                        w = w_base if p_idx == 0 else (w_base // 2)
                        penalties.append(self.t_day_active[t_id, fd_idx] * w)

        # C. DESIDERATA AVANZATI: Ingressi Posticipati & Uscite Anticipate (Pesi bilanciati per non frammentare l'orario)
        if not skip_penalties:
            for t_id, teacher in prob.teachers.items():
                t_assignments = [a for a in prob.assignments if a.teacher_id == t_id]
                l_days = getattr(teacher, "late_entry_days", [])
                if l_days:
                    for day_name in l_days:
                        d_idx = self._get_day_index(day_name)
                        if d_idx is not None and d_idx < num_days:
                            penalties.append(sum(self.x[a.id, d_idx, 0] for a in t_assignments) * 10)
                elif teacher.prefer_late_entry:
                    for d in range(num_days):
                        penalties.append(sum(self.x[a.id, d, 0] for a in t_assignments) * 5)

                e_days = getattr(teacher, "early_exit_days", [])
                if e_days:
                    for day_name in e_days:
                        d_idx = self._get_day_index(day_name)
                        if d_idx is not None and d_idx < num_days:
                            H = daily_hours[d_idx]
                            if H > 0:
                                penalties.append(sum(self.x[a.id, d_idx, H - 1] for a in t_assignments) * 10)
                elif teacher.prefer_early_exit:
                    for d in range(num_days):
                        H = daily_hours[d]
                        if H > 0:
                            penalties.append(sum(self.x[a.id, d, H - 1] for a in t_assignments) * 5)

        # D. DESIDERATA: Slot Sconsigliati (Evita se possibile)
        if not skip_penalties:
            for t_id, teacher in prob.teachers.items():
                t_assignments = [a for a in prob.assignments if a.teacher_id == t_id]
                for avoid_slot in getattr(teacher, "soft_avoid_slots", []):
                    if len(avoid_slot) == 2:
                        d_idx, h_idx = avoid_slot
                        if d_idx < num_days and h_idx < daily_hours[d_idx]:
                            penalties.append(sum(self.x[a.id, d_idx, h_idx] for a in t_assignments) * 15)

        # E. DESIDERATA DIDATTICO: Ore Doppie / Consecutività (Blocchi 2h e Blocco 3h Tema Italiano)
        force_triple_ita_school = getattr(prob.config, "force_triple_hours_italian", False)
        for a in prob.assignments:
            is_ita = (a.subject_id == "ita" or "italian" in a.subject_id.lower())
            is_force_triple = is_ita and (force_triple_ita_school or getattr(a, "force_triple_hours", False))

            if is_force_triple and a.hours_per_week >= 3:
                day_triplets = []
                for d in range(num_days):
                    H = daily_hours[d]
                    if H >= 3:
                        d_trips = []
                        for h in range(H - 2):
                            trip_var = m.NewBoolVar(f"trip_{a.id}_d{d}_h{h}")
                            m.AddBoolAnd([self.x[a.id, d, h], self.x[a.id, d, h + 1], self.x[a.id, d, h + 2]]).OnlyEnforceIf(trip_var)
                            d_trips.append(trip_var)
                        day_has_trip = m.NewBoolVar(f"d_trip_{a.id}_{d}")
                        m.AddMaxEquality(day_has_trip, d_trips)
                        day_triplets.append(day_has_trip)
                        
                        m.Add(sum(self.x[a.id, d, h] for h in range(H)) == 3).OnlyEnforceIf(day_has_trip)
                        m.Add(sum(self.x[a.id, d, h] for h in range(H)) <= 2).OnlyEnforceIf(day_has_trip.Not())

                if day_triplets:
                    m.Add(sum(day_triplets) == 1)
            else:
                is_force_double = a.force_double_hours
                if hasattr(prob.config, "subject_block_preferences") and prob.config.subject_block_preferences:
                    if a.subject_id in prob.config.subject_block_preferences:
                        is_force_double = bool(prob.config.subject_block_preferences[a.subject_id])

                if is_force_double and a.hours_per_week >= 2:
                    day_pairs = []
                    is_dada_strict_pairs = getattr(prob.config, "is_dada", False) and getattr(prob.config, "dada_strict_even_pairs", False)
                    a_pairs = []
                    for d in range(num_days):
                        H = daily_hours[d]
                        if H >= 2:
                            allowed_h_starts = [h for h in range(0, H - 1, 2)] if is_dada_strict_pairs else [h for h in range(H - 1)]
                            for h in allowed_h_starts:
                                pair_var = m.NewBoolVar(f"pair_{a.id}_d{d}_h{h}")
                                m.AddBoolAnd([self.x[a.id, d, h], self.x[a.id, d, h + 1]]).OnlyEnforceIf(pair_var)
                                m.AddBoolOr([self.x[a.id, d, h].Not(), self.x[a.id, d, h + 1].Not()]).OnlyEnforceIf(pair_var.Not())
                                a_pairs.append(pair_var)
                                self.all_pair_vars.append(pair_var)
                        # In ogni giorno ci può essere al massimo 1 blocco da 2 ore per questa materia
                        m.Add(sum(self.x[a.id, d, h] for h in range(H)) <= 2)

                    if a_pairs:
                        target_pairs = a.hours_per_week // 2
                        # Vincolo rigido matematico: 100% dei blocchi da 2 ore garantiti accoppiati
                        m.Add(sum(a_pairs) == target_pairs)

        # E-bis. MINIMIZZAZIONE USO SPAZI SECONDARI / EMERGENZA (Priorità Aule & Palestre)
        # Se un gruppo di aule contiene spazi a priorità differenziata (es. Palestra Principale Priorità 1 vs Emergenza Priorità 2),
        # penalizza l'uso di spazi secondari quando il numero di classi contemporanee eccede la capienza degli spazi di priorità superiore.
        if not skip_penalties:
            for comp_rooms_tuple, assign_ids in room_group_map.items():
                rooms_in_group = [prob.rooms[r_id] for r_id in comp_rooms_tuple if r_id in prob.rooms]
                prio1_cap = sum(r.capacity for r in rooms_in_group if getattr(r, "priority", 1) == 1)
                total_cap = sum(r.capacity for r in rooms_in_group)
                
                if 0 < prio1_cap < total_cap:
                    total_h_in_group = sum(prob.assignments_by_id[a_id].hours_per_week for a_id in assign_ids if hasattr(prob, "assignments_by_id") and a_id in prob.assignments_by_id) if hasattr(prob, "assignments_by_id") else sum(a.hours_per_week for a in prob.assignments if a.id in assign_ids)
                    total_slots = sum(daily_hours[:num_days])
                    
                    group_overflow_vars = []
                    for d in range(num_days):
                        for h in range(daily_hours[d]):
                            active_in_slot = [self.x[a_id, d, h] for a_id in assign_ids]
                            overflow_var = m.NewIntVar(0, total_cap - prio1_cap, f"overflow_prio_{abs(hash(comp_rooms_tuple))}_d{d}_h{h}")
                            m.Add(sum(active_in_slot) - prio1_cap <= overflow_var)
                            group_overflow_vars.append(overflow_var)
                            penalties.append(overflow_var * 1500)

        # F. FORMULAZIONE DELLE ORE BUCHE & EQUITÀ MIN-MAX (Compressione Massima Buche)
        if not skip_penalties:
            strict = self.strict_gap_limit if self.strict_gap_limit is not None else criteria.strict_gap_limit
            user_max_gaps = int(self.max_gap_limit if self.max_gap_limit is not None else getattr(criteria, "max_gap_limit", 2))

            for t_id, teacher in prob.teachers.items():
                t_assignments = [a for a in prob.assignments if a.teacher_id == t_id]
                t_gaps_list = []
                for d in range(num_days):
                    H = daily_hours[d]
                    if H <= 2:
                        continue
                    
                    u = {}
                    for h in range(H):
                        u[h] = sum(self.x[a.id, d, h] for a in t_assignments)
                    
                    for h in range(1, H - 1):
                        has_earlier = m.NewBoolVar(f"he_{t_id}_{d}_{h}")
                        has_later = m.NewBoolVar(f"hl_{t_id}_{d}_{h}")
                        m.Add(sum(u[k] for k in range(0, h)) >= 1).OnlyEnforceIf(has_earlier)
                        m.Add(sum(u[k] for k in range(0, h)) == 0).OnlyEnforceIf(has_earlier.Not())
                        m.Add(sum(u[k] for k in range(h + 1, H)) >= 1).OnlyEnforceIf(has_later)
                        m.Add(sum(u[k] for k in range(h + 1, H)) == 0).OnlyEnforceIf(has_later.Not())
                        
                        gap_h = m.NewBoolVar(f"gap_{t_id}_{d}_{h}")
                        m.Add(gap_h >= has_earlier + has_later - 1 - u[h])
                        t_gaps_list.append(gap_h)
                        penalties.append(gap_h * max(getattr(criteria, "weight_gap_hours", 1200), 1200))

                if t_gaps_list:
                    t_tot_gaps = m.NewIntVar(0, 30, f"tot_gaps_{t_id}")
                    m.Add(t_tot_gaps == sum(t_gaps_list))
                    if strict:
                        m.Add(t_tot_gaps <= user_max_gaps)
                    else:
                        excess_g = m.NewIntVar(0, 30, f"exg_{t_id}")
                        m.Add(excess_g >= t_tot_gaps - user_max_gaps)
                        penalties.append(excess_g * 2500)

            # Minimizza la somma di tutte le penalità
            if penalties:
                m.Minimize(sum(penalties))

        # Strategia di ramificazione intelligente per concentrare la ricerca sui blocchi da 2h
        if self.all_pair_vars:
            m.AddDecisionStrategy(self.all_pair_vars, cp_model.CHOOSE_FIRST, cp_model.SELECT_MAX_VALUE)

    def solve(self, max_time_seconds: int = 45, random_seed: int = 42) -> TimetableResult:
        start_time = time.time()
        
        status_map = {
            cp_model.OPTIMAL: "OPTIMAL",
            cp_model.FEASIBLE: "FEASIBLE",
            cp_model.INFEASIBLE: "INFEASIBLE",
            cp_model.MODEL_INVALID: "INVALID",
            cp_model.UNKNOWN: "UNKNOWN"
        }
        
        # -------------------------------------------------------------
        # FASE 1: Risoluzione rapida di FATTIBILITÀ SAT (100% vincoli rigidi e ore doppie)
        # -------------------------------------------------------------
        self.model = cp_model.CpModel()
        self.x.clear()
        self.y_room.clear()
        self.t_active.clear()
        self.t_day_active.clear()
        self.t_gap.clear()
        self.all_pair_vars.clear()
        self.build_model(skip_penalties=True)
        
        solver_feas = cp_model.CpSolver()
        solver_feas.parameters.max_time_in_seconds = max_time_seconds
        solver_feas.parameters.num_workers = 8
        solver_feas.parameters.random_seed = random_seed
        solver_feas.parameters.cp_model_presolve = True
        
        feas_code = solver_feas.Solve(self.model)
        feas_status = status_map.get(feas_code, "UNKNOWN")
        elapsed = time.time() - start_time
        
        if feas_status not in ["OPTIMAL", "FEASIBLE"]:
            return self._extract_result(solver_feas, feas_status, elapsed, 0.0, max_time_seconds)
            
        res_feas = self._extract_result(solver_feas, feas_status, elapsed, 0.0, max_time_seconds)
        
        # -------------------------------------------------------------
        # FASE 2: Ottimizzazione Avanzata & Compressione Buche con Warm Start
        # -------------------------------------------------------------
        t_remaining = max_time_seconds - int(elapsed)
        if t_remaining >= 3:
            hints_x = {k: solver_feas.Value(v) for k, v in self.x.items()}
            
            self.model = cp_model.CpModel()
            self.x.clear()
            self.y_room.clear()
            self.t_active.clear()
            self.t_day_active.clear()
            self.t_gap.clear()
            self.all_pair_vars.clear()
            self.build_model(skip_penalties=False)
            
            # Inietta la soluzione di Fase 1 come hint
            for k, val in hints_x.items():
                if k in self.x:
                    self.model.AddHint(self.x[k], val)
                    
            solver_opt = cp_model.CpSolver()
            solver_opt.parameters.max_time_in_seconds = t_remaining
            solver_opt.parameters.num_workers = 8
            solver_opt.parameters.random_seed = random_seed
            solver_opt.parameters.search_branching = cp_model.PORTFOLIO_SEARCH
            solver_opt.parameters.cp_model_presolve = True
            
            opt_code = solver_opt.Solve(self.model)
            opt_status = status_map.get(opt_code, "UNKNOWN")
            if opt_status in ["OPTIMAL", "FEASIBLE"]:
                return self._extract_result(solver_opt, opt_status, time.time() - start_time, solver_opt.ObjectiveValue(), max_time_seconds)

        return res_feas

    def _extract_result(self, active_solver: cp_model.CpSolver, status_str: str, elapsed: float, obj_val: float, max_time_seconds: int = 45) -> TimetableResult:
        res = TimetableResult(
            status=status_str,
            solve_time=round(elapsed, 2),
            objective_value=obj_val
        )
        
        if status_str not in ["OPTIMAL", "FEASIBLE"]:
            issues = diagnose_problem_feasibility(self.problem)
            user_max_gaps = int(self.max_gap_limit if self.max_gap_limit is not None else getattr(self.problem.config.optimization_criteria, "max_gap_limit", 5))
            strict = self.strict_gap_limit if self.strict_gap_limit is not None else getattr(self.problem.config.optimization_criteria, "strict_gap_limit", False)
            
            if strict:
                issues.append(f"🔒 **Vincolo Tassativo Ore Buche (max {user_max_gaps}h)**: Con {len(self.problem.classes)} classi e i vincoli attuali, un tetto rigido di {user_max_gaps}h potrebbe essere troppo restrittivo entro {max_time_seconds}s. Prova ad aumentare il tempo a disposizione o a rilassare leggermente il limite a {user_max_gaps + 1}h.")
            
            if issues:
                res.log_messages.extend(issues)
            else:
                res.log_messages.append(f"Il solutore ha restituito stato: {status_str}. Nessuna combinazione valida trovata entro il tempo limite di {max_time_seconds}s.")
            return res

        prob = self.problem
        num_days = self.num_days
        daily_hours = self.daily_hours
        
        for c_id in prob.classes:
            res.grid_by_class[c_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]
            
        for t_id in prob.teachers:
            res.grid_by_teacher[t_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]

        for r_id in prob.rooms:
            res.grid_by_room[r_id] = [[None for _ in range(daily_hours[d])] for d in range(num_days)]

        # Assegnazione atomica e coerente delle aule per BLOCCHI CONTINUI di lezione
        # In ogni giorno, per ciascuna cattedra attiva, si individua il blocco consecutivo di ore [h_start..h_end].
        # L'aula viene scelta in modo da essere LIBERA per l'INTERA DURATA DEL BLOCCO e assegnata stabilmente per tutte le ore.
        room_occupancy: Dict[Tuple[str, int, int], List[str]] = {}
        assigned_room_by_slot: Dict[Tuple[str, int, int], Tuple[Optional[str], Optional[str]]] = {}

        for d in range(num_days):
            # Identifica tutti i blocchi contigui di lezione nel giorno d
            day_blocks = []
            for a in prob.assignments:
                active_h = [h for h in range(daily_hours[d]) if active_solver.Value(self.x[a.id, d, h]) == 1]
                if not active_h:
                    continue
                # Raggruppa in segmenti contigui
                curr_block = [active_h[0]]
                for h_next in active_h[1:]:
                    if h_next == curr_block[-1] + 1:
                        curr_block.append(h_next)
                    else:
                        day_blocks.append((a, list(curr_block)))
                        curr_block = [h_next]
                if curr_block:
                    day_blocks.append((a, list(curr_block)))

            # Ordina i blocchi del giorno: prima i blocchi più lunghi (2h/3h) e con vincoli aula più stringenti
            def block_sort_key(item):
                a_obj, h_list = item
                comp = self.assignment_compatible_rooms.get(a_obj.id, [])
                has_pref = 0 if a_obj.preferred_room_id else 1
                return (has_pref, -len(h_list), len(comp), a_obj.id)

            day_blocks.sort(key=block_sort_key)

            # Assegna una sola aula stabile e costante per ciascun intero blocco
            for a, h_list in day_blocks:
                comp_rooms = self.assignment_compatible_rooms.get(a.id, [])
                subj = prob.subjects.get(a.subject_id)
                assigned_r_id = None
                assigned_r_name = None

                if comp_rooms:
                    sorted_comp = sorted(comp_rooms, key=lambda r_id: getattr(prob.rooms.get(r_id), "priority", 1) if r_id in prob.rooms else 1)
                    # Cerca un'aula che sia libera per TUTTE le ore del blocco
                    for r_id in sorted_comp:
                        if r_id in prob.rooms:
                            r_cap = prob.rooms[r_id].capacity
                            can_fit_all = all(
                                len(room_occupancy.get((r_id, d, h), [])) < r_cap
                                for h in h_list
                            )
                            if can_fit_all:
                                assigned_r_id = r_id
                                assigned_r_name = prob.rooms[r_id].name
                                break
                    # Fallback di sicurezza: prima aula compatibile
                    if assigned_r_id is None:
                        for r_id in sorted_comp:
                            if r_id in prob.rooms:
                                assigned_r_id = r_id
                                assigned_r_name = prob.rooms[r_id].name
                                break
                elif subj and subj.special_room_id and subj.special_room_id in prob.rooms:
                    assigned_r_id = subj.special_room_id
                    assigned_r_name = prob.rooms[subj.special_room_id].name

                # Registra la stessa identica aula per TUTTE le ore del blocco
                for h in h_list:
                    assigned_room_by_slot[a.id, d, h] = (assigned_r_id, assigned_r_name)
                    if assigned_r_id:
                        room_occupancy.setdefault((assigned_r_id, d, h), []).append(a.id)

        for d in range(num_days):
            for h in range(daily_hours[d]):
                active_assigns_in_slot = [a for a in prob.assignments if active_solver.Value(self.x[a.id, d, h]) == 1]
                slot_info_list = []
                for a in active_assigns_in_slot:
                    subj = prob.subjects.get(a.subject_id)
                    teacher = prob.teachers.get(a.teacher_id)
                    school_class = prob.classes.get(a.class_id)
                    assigned_room_id, assigned_room_name = assigned_room_by_slot.get((a.id, d, h), (None, None))
                    co_t_names = [prob.teachers[ct].name for ct in a.co_teacher_ids if ct in prob.teachers]

                    slot_info = LessonSlotInfo(
                        assignment_id=a.id,
                        class_id=a.class_id,
                        class_name=school_class.name if school_class else a.class_id,
                        teacher_id=a.teacher_id,
                        teacher_name=teacher.name if teacher else a.teacher_id,
                        subject_id=a.subject_id,
                        subject_name=subj.name if subj else a.subject_id,
                        subject_color=subj.color if subj else "#3498db",
                        room_id=assigned_room_id,
                        room_name=assigned_room_name,
                        co_teachers=co_t_names
                    )
                    slot_info_list.append((a, assigned_room_id, slot_info))

                # Post-processing per identificare le compresenze (co-docenti, classi aperte, condivisione aula)
                active_parallel_groups = [pg for pg in getattr(prob.config, "parallel_groups", []) if pg.is_active]
                for a_item, r_id, s_info in slot_info_list:
                    comp_desc_parts = []
                    
                    # 1. Co-docenti su stessa cattedra (es. sostegno / ITP)
                    if s_info.co_teachers:
                        s_info.is_compresenza = True
                        comp_desc_parts.append(f"Compresenza con {', '.join(s_info.co_teachers)}")
                        
                    # 2. Gruppi di Classi Aperte / Parallelismi
                    for grp in active_parallel_groups:
                        if a_item.class_id in grp.class_ids and a_item.subject_id == grp.subject_id:
                            is_group_parallel_slot = False
                            p_vars = getattr(self, "parallel_group_slot_vars", {}).get(grp.id)
                            if p_vars is not None:
                                if (d, h) in p_vars and active_solver.Value(p_vars[d, h]) == 1:
                                    is_group_parallel_slot = True
                            else:
                                other_in_grp = [
                                    (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                    if oa.class_id in grp.class_ids and oa.class_id != a_item.class_id and oa.subject_id == grp.subject_id
                                ]
                                if len(other_in_grp) == len(grp.class_ids) - 1:
                                    is_group_parallel_slot = True

                            if is_group_parallel_slot:
                                other_active_in_grp = [
                                    (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                    if oa.class_id in grp.class_ids and oa.class_id != a_item.class_id and oa.subject_id == grp.subject_id
                                ]
                                if other_active_in_grp:
                                    s_info.is_compresenza = True
                                    other_c_names = [os_info.class_name for (_, _, os_info) in other_active_in_grp]
                                    other_t_names = [os_info.teacher_name for (_, _, os_info) in other_active_in_grp if os_info.teacher_id != s_info.teacher_id]
                                    s_info.parallel_classes = other_c_names
                                    s_info.parallel_teachers = other_t_names
                                    
                                    if other_t_names:
                                        comp_desc_parts.append(f"Classi Aperte con {', '.join(other_c_names)} ({', '.join(other_t_names)})")
                                    else:
                                        comp_desc_parts.append(f"Classi Aperte con {', '.join(other_c_names)}")
                                    
                    # 3. Stessa Aula / Palestra condivisa con altre classi nello stesso momento
                    if r_id and r_id in prob.rooms:
                        room_obj = prob.rooms[r_id]
                        if room_obj.capacity > 1 or room_obj.is_special_lab or "palestra" in r_id.lower() or "palestra" in room_obj.name.lower():
                            same_room_other = [
                                (oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list
                                if occ_r == r_id and oa.id != a_item.id and (oa.class_id not in s_info.parallel_classes)
                            ]
                            if same_room_other:
                                s_info.is_compresenza = True
                                other_c_names = [os_info.class_name for (_, _, os_info) in same_room_other]
                                other_t_names = [os_info.teacher_name for (_, _, os_info) in same_room_other if os_info.teacher_id != s_info.teacher_id]
                                if other_t_names:
                                    comp_desc_parts.append(f"Spazio {s_info.room_name} con {', '.join(other_c_names)} ({', '.join(other_t_names)})")
                                else:
                                    comp_desc_parts.append(f"Spazio {s_info.room_name} con {', '.join(other_c_names)}")
                                
                    if comp_desc_parts:
                        s_info.compresenza_text = " | ".join(comp_desc_parts)

                    # Inserimento nelle griglie
                    res.grid_by_class[a_item.class_id][d][h] = s_info
                    res.grid_by_teacher[a_item.teacher_id][d][h] = s_info
                    
                    for ct_id in a_item.co_teacher_ids:
                        if ct_id in res.grid_by_teacher:
                            res.grid_by_teacher[ct_id][d][h] = s_info

                # Popolamento griglia per Aula/Spazio
                for r_id_key in prob.rooms:
                    room_slots = [(oa, occ_r, os_info) for (oa, occ_r, os_info) in slot_info_list if occ_r == r_id_key]
                    if len(room_slots) == 1:
                        res.grid_by_room[r_id_key][d][h] = room_slots[0][2]
                    elif len(room_slots) > 1:
                        all_c_names = " + ".join([os_info.class_name for (_, _, os_info) in room_slots])
                        all_t_names = " + ".join(list(dict.fromkeys([os_info.teacher_name for (_, _, os_info) in room_slots])))
                        s_first = room_slots[0][2]
                        combined_room_slot = LessonSlotInfo(
                            assignment_id=s_first.assignment_id,
                            class_id="compresenza",
                            class_name=f"{all_c_names}",
                            teacher_id="compresenza",
                            teacher_name=f"{all_t_names}",
                            subject_id=s_first.subject_id,
                            subject_name=s_first.subject_name,
                            subject_color=s_first.subject_color,
                            room_id=r_id_key,
                            room_name=s_first.room_name,
                            is_compresenza=True,
                            compresenza_text=f"Compresenza ({len(room_slots)} Classi in contemporanea)"
                        )
                        res.grid_by_room[r_id_key][d][h] = combined_room_slot

        # ---------------------------------------------------------
        # Calcolo Statistiche sui Desiderata
        # ---------------------------------------------------------
        # 1. Giorno Libero
        for t_id, teacher in prob.teachers.items():
            t_grid = res.grid_by_teacher.get(t_id, [])
            t_assignments = [a for a in prob.assignments if a.teacher_id == t_id or t_id in a.co_teacher_ids]
            t_total_h = sum(a.hours_per_week for a in t_assignments)
            can_have_free_day = (num_days == 6) or teacher.is_part_time or (t_total_h <= 14)
            
            if can_have_free_day:
                fd1 = self._get_day_index(teacher.free_day_1)
                if fd1 is not None:
                    res.free_days_total_first += 1
                    if len(t_grid) > fd1 and all(h_cell is None for h_cell in t_grid[fd1]):
                        res.free_days_satisfied_first += 1
                        
                fd2 = self._get_day_index(teacher.free_day_2)
                if fd2 is not None:
                    res.free_days_total_second += 1
                    if len(t_grid) > fd2 and all(h_cell is None for h_cell in t_grid[fd2]):
                        res.free_days_satisfied_second += 1

        # 2. Ore Buche calcolate direttamente dalla griglia oraria effettiva
        total_gaps = 0
        for t_id, teacher in prob.teachers.items():
            t_gaps = 0
            t_grid = res.grid_by_teacher.get(t_id, [])
            for d in range(num_days):
                active_hours = [h for h in range(daily_hours[d]) if t_grid and d < len(t_grid) and h < len(t_grid[d]) and t_grid[d][h] is not None]
                if len(active_hours) >= 2:
                    first_h = min(active_hours)
                    last_h = max(active_hours)
                    span = last_h - first_h + 1
                    worked = len(active_hours)
                    t_gaps += (span - worked)
            res.gaps_by_teacher[t_id] = t_gaps
            total_gaps += t_gaps
        res.total_gap_hours = total_gaps

        # 3. Ore doppie verificate per singola materia flaggata nel Tab Configurazione
        res.double_hours_by_subject = {}
        for s_id, s in prob.subjects.items():
            is_flagged = False
            if hasattr(prob.config, "subject_block_preferences") and prob.config.subject_block_preferences:
                is_flagged = bool(prob.config.subject_block_preferences.get(s_id, False))
            
            s_assigns = [a for a in prob.assignments if a.subject_id == s_id and a.hours_per_week >= 2]
            if not s_assigns:
                continue
                
            sat_count = 0
            tot_count = len(s_assigns)
            
            for a in s_assigns:
                has_adj = False
                for d in range(num_days):
                    for h in range(daily_hours[d] - 1):
                        if active_solver.Value(self.x[a.id, d, h]) == 1 and active_solver.Value(self.x[a.id, d, h + 1]) == 1:
                            has_adj = True
                            break
                    if has_adj:
                        break
                if has_adj:
                    sat_count += 1
                    
            pct = round(sat_count / tot_count * 100) if tot_count > 0 else 100
            res.double_hours_by_subject[s_id] = {
                "name": s.name,
                "is_flagged": is_flagged,
                "total": tot_count,
                "satisfied": sat_count,
                "pct": pct
            }
            if is_flagged:
                res.double_hours_total += tot_count
                res.double_hours_satisfied += sat_count

        # 3bis. Blocco da 3 Ore Consecutive (Tema di Italiano)
        force_triple_ita = getattr(prob.config, "force_triple_hours_italian", False)
        ita_assignments = [a for a in prob.assignments if a.subject_id in ["ita", "lettere", "italiano"] and (getattr(a, "force_triple_hours", False) or force_triple_ita)]
        if ita_assignments:
            trip_sat = 0
            trip_tot = len(ita_assignments)
            for a in ita_assignments:
                has_trip = False
                for d in range(num_days):
                    for h in range(daily_hours[d] - 2):
                        if active_solver.Value(self.x[a.id, d, h]) == 1 and active_solver.Value(self.x[a.id, d, h + 1]) == 1 and active_solver.Value(self.x[a.id, d, h + 2]) == 1:
                            has_trip = True
                            break
                    if has_trip:
                        break
                if has_trip:
                    trip_sat += 1
            res.triple_hours_total = trip_tot
            res.triple_hours_satisfied = trip_sat
            res.triple_hours_pct = round(trip_sat / trip_tot * 100) if trip_tot > 0 else 100
        else:
            res.triple_hours_total = 0
            res.triple_hours_satisfied = 0
            res.triple_hours_pct = 100

        # 4. Desiderata Avanzati (Entrare tardi / Uscire presto / Slot puntuali)
        for t_id, teacher in prob.teachers.items():
            t_grid = res.grid_by_teacher.get(t_id, [])
            # Ingressi posticipati (No 1ª ora nei giorni specificati)
            l_days = getattr(teacher, "late_entry_days", [])
            if l_days:
                for day_name in l_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and d_idx < num_days:
                        res.late_entry_total += 1
                        if len(t_grid) > d_idx and len(t_grid[d_idx]) > 0 and t_grid[d_idx][0] is None:
                            res.late_entry_satisfied += 1
            elif teacher.prefer_late_entry:
                res.late_entry_total += 1
                if any(len(t_grid) > d and len(t_grid[d]) > 0 and t_grid[d][0] is None for d in range(num_days)):
                    res.late_entry_satisfied += 1

            # Uscite anticipate (No ultima ora nei giorni specificati)
            e_days = getattr(teacher, "early_exit_days", [])
            if e_days:
                for day_name in e_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and d_idx < num_days:
                        H = daily_hours[d_idx]
                        if H > 0:
                            res.early_exit_total += 1
                            if len(t_grid) > d_idx and len(t_grid[d_idx]) >= H and t_grid[d_idx][H - 1] is None:
                                res.early_exit_satisfied += 1
            elif teacher.prefer_early_exit:
                res.early_exit_total += 1
                if any(daily_hours[d] > 0 and len(t_grid) > d and len(t_grid[d]) >= daily_hours[d] and t_grid[d][daily_hours[d] - 1] is None for d in range(num_days)):
                    res.early_exit_satisfied += 1

            # Slot puntuali sconsigliati
            for slot in teacher.soft_avoid_slots:
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        res.soft_slots_total += 1
                        if len(t_grid) > d and len(t_grid[d]) > h and t_grid[d][h] is None:
                            res.soft_slots_satisfied += 1

        # 5. Generazione Report di Soddisfazione Dettagliato per Docente
        teacher_reports = {}
        total_scores = []
        for t_id, teacher in prob.teachers.items():
            t_grid = res.grid_by_teacher.get(t_id, [])
            
            # Calcolo giorni effettivi di presenza
            active_d_indices = []
            for d in range(num_days):
                if any(t_grid[d][h] is not None for h in range(daily_hours[d])):
                    active_d_indices.append(d)
            
            assigned_free_days = [DAYS_OF_WEEK[d] for d in range(num_days) if d not in active_d_indices]
            
            # Desiderata Giorno Libero
            req_fds = getattr(teacher, "free_days", [])
            if not req_fds:
                req_fds = []
                if teacher.free_day_1: req_fds.append(teacher.free_day_1)
                if teacher.free_day_2: req_fds.append(teacher.free_day_2)
                
            can_have_fd = (num_days == 6) or teacher.is_part_time
            fd_status = "N/A (Tempo pieno 5gg)"
            fd_satisfied_count = 0
            if can_have_fd:
                if req_fds:
                    satisfied_fds = [d for d in req_fds if d in assigned_free_days]
                    fd_satisfied_count = len(satisfied_fds)
                    if fd_satisfied_count == len(req_fds):
                        fd_status = f"✅ 100% Concesso ({', '.join(satisfied_fds)})"
                    elif fd_satisfied_count > 0:
                        fd_status = f"🟡 Parziale ({', '.join(satisfied_fds)} su {', '.join(req_fds)})"
                    else:
                        fd_status = f"❌ Non concesso (Assegnato: {', '.join(assigned_free_days) if assigned_free_days else 'Nessuno'})"
                else:
                    fd_status = f"ℹ️ Assegnato: {', '.join(assigned_free_days) if assigned_free_days else 'Nessuno'}"
            
            # Ingressi posticipati (No 1ª ora nei giorni specificati)
            late_entry_ok = 0
            late_entry_total = 0
            l_days = getattr(teacher, "late_entry_days", [])
            if l_days:
                late_entry_total = len(l_days)
                for day_name in l_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None and len(t_grid) > d_idx and len(t_grid[d_idx]) > 0 and t_grid[d_idx][0] is None:
                        late_entry_ok += 1
            elif teacher.prefer_late_entry:
                late_entry_total = 1
                if any(len(t_grid) > d and len(t_grid[d]) > 0 and t_grid[d][0] is None for d in active_d_indices):
                    late_entry_ok = 1

            # Uscite anticipate (No ult. ora nei giorni specificati)
            early_exit_ok = 0
            early_exit_total = 0
            e_days = getattr(teacher, "early_exit_days", [])
            if e_days:
                early_exit_total = len(e_days)
                for day_name in e_days:
                    d_idx = self._get_day_index(day_name)
                    if d_idx is not None:
                        H = daily_hours[d_idx]
                        if H > 0 and len(t_grid) > d_idx and len(t_grid[d_idx]) >= H and t_grid[d_idx][H - 1] is None:
                            early_exit_ok += 1
            elif teacher.prefer_early_exit:
                early_exit_total = 1
                if any(daily_hours[d] > 0 and len(t_grid) > d and len(t_grid[d]) >= daily_hours[d] and t_grid[d][daily_hours[d] - 1] is None for d in active_d_indices):
                    early_exit_ok = 1

            # Ore buche del docente
            t_gaps = res.gaps_by_teacher.get(t_id, 0)
            
            # Slot puntuali sconsigliati
            soft_slots_ok = 0
            soft_slots_total = len(teacher.soft_avoid_slots)
            for slot in teacher.soft_avoid_slots:
                if len(slot) == 2:
                    d, h = slot[0], slot[1]
                    if d < num_days and h < daily_hours[d]:
                        if len(t_grid) > d and len(t_grid[d]) > h and t_grid[d][h] is None:
                            soft_slots_ok += 1

            # Ore doppie relative al docente
            t_double_ok = 0
            t_double_total = 0
            for a in prob.assignments:
                if (a.teacher_id == t_id or t_id in a.co_teacher_ids) and a.force_double_hours:
                    t_double_total += 1
                    for d in range(num_days):
                        for h in range(daily_hours[d] - 1):
                            if active_solver.Value(self.x[a.id, d, h]) == 1 and active_solver.Value(self.x[a.id, d, h + 1]) == 1:
                                t_double_ok += 1
                                break

            # Calcolo Punteggio % Soddisfazione (0 - 100)
            score_points = 100.0
            
            if can_have_fd and req_fds:
                if fd_satisfied_count == 0:
                    score_points -= 25.0
                elif fd_satisfied_count < len(req_fds):
                    score_points -= 10.0
                    
            if late_entry_total > 0:
                late_ratio = late_entry_ok / late_entry_total
                score_points -= (1.0 - late_ratio) * 15.0
                
            if early_exit_total > 0:
                early_ratio = early_exit_ok / early_exit_total
                score_points -= (1.0 - early_ratio) * 15.0
                
            if soft_slots_total > 0:
                soft_ratio = soft_slots_ok / soft_slots_total
                score_points -= (1.0 - soft_ratio) * 20.0
                
            if t_gaps > teacher.max_gap_hours:
                score_points -= min(25.0, (t_gaps - teacher.max_gap_hours) * 10.0)
            elif t_gaps > 0:
                score_points -= min(10.0, t_gaps * 3.0)

            score_final = max(0.0, min(100.0, score_points))
            total_scores.append(score_final)
            
            if score_final >= 90:
                status_badge = "🟢 100% Soddisfatto" if score_final >= 99 else f"🟢 Ottimo ({int(score_final)}%)"
            elif score_final >= 70:
                status_badge = f"🟡 Buono ({int(score_final)}%)"
            else:
                status_badge = f"🔴 Da Verificare ({int(score_final)}%)"

            teacher_reports[t_id] = {
                "name": teacher.name,
                "cdc": getattr(teacher, "cdc", ""),
                "is_part_time": teacher.is_part_time,
                "contract_hours": getattr(teacher, "contract_hours", 18),
                "working_days_count": len(active_d_indices),
                "assigned_free_days": assigned_free_days,
                "requested_free_days": req_fds,
                "free_day_status": fd_status,
                "prefer_late_entry": teacher.prefer_late_entry,
                "late_entry_result": f"{late_entry_ok}/{late_entry_total} gg" if late_entry_total > 0 else "-",
                "prefer_early_exit": teacher.prefer_early_exit,
                "early_exit_result": f"{early_exit_ok}/{early_exit_total} gg" if early_exit_total > 0 else "-",
                "gap_hours": t_gaps,
                "soft_slots_result": f"{soft_slots_ok}/{soft_slots_total}" if soft_slots_total > 0 else "-",
                "double_hours_result": f"{t_double_ok}/{t_double_total}" if t_double_total > 0 else "-",
                "score_percent": round(score_final, 1),
                "status_badge": status_badge
            }

        res.teacher_reports = teacher_reports
        res.global_satisfaction_score = round(sum(total_scores) / len(total_scores), 1) if total_scores else 100.0

        return res
