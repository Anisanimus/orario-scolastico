"""
Dati di esempio realistici per la SCUOLA SECONDARIA DI I GRADO (SCUOLA MEDIA).
Generatore dinamico parametrizzabile per qualsiasi numero di classi (es. 3, 6, 9, 12, 15, 18, 24 classi).
Monte ore e cattedre perfette al 100%:
- 30 ore settimanali esatte per ciascuna classe (Quadro DPR 89/2009).
- Docenti a Tempo Pieno: ESATTAMENTE 18 ORE CIASCUNO (CCNL Scuola).
- Docenti Part-Time / Spezzoni: 12h o 6h bilanciate.
"""
from typing import Dict, List, Optional, Tuple
from models import (
    SchoolConfig, Teacher, SchoolClass, Subject, Classroom, 
    TeachingAssignment, TimetableProblem, DAYS_OF_WEEK
)

# Pool di cognomi realistici per docenti italiani
TEACHER_NAMES = [
    "Prof.ssa Bianchi", "Prof. Romano", "Prof.ssa Marino", "Prof. Verdi",
    "Prof.ssa Ferrari", "Prof.ssa Rossi", "Prof. Russo", "Prof.ssa Ricci",
    "Prof. Conti", "Prof. De Luca", "Prof.ssa Fontana", "Prof.ssa Gallo",
    "Prof. Costa", "Prof.ssa Giordano", "Prof. Mancini", "Prof. Rizzo",
    "Prof.ssa Lombardi", "Prof. Moretti", "Prof.ssa Barbieri", "Prof.ssa Santoro",
    "Prof. Marini", "Prof.ssa Rinaldi", "Prof. Caruso", "Prof.ssa Ferrara",
    "Prof. Galli", "Prof.ssa Martini", "Prof. Leone", "Prof.ssa Longo",
    "Prof. Gentile", "Prof.ssa Martinelli", "Prof. Vitale", "Prof.ssa Serra",
    "Prof. Coppola", "Prof.ssa Amato", "Prof. Fabbri", "Prof.ssa Gatti",
    "Prof. Pellegrini", "Prof.ssa Palumbo", "Prof. Sanna", "Prof.ssa Grasso"
]

def get_sample_problem(num_classes: int = 18, is_dada: bool = False, second_lang: str = "Spagnolo", with_theater: bool = False) -> TimetableProblem:
    """
    Genera un problema realistico per una scuola media con `num_classes` classi (predefinito: 18 classi)
    e la seconda lingua comunitaria scelta (Spagnolo, Francese, Tedesco, ecc.).
    Se `with_theater=True`, attiva il Laboratorio di Teatro (1h per classe) scalando 1h da Italiano (5h)
    e assegnando 1-2h di Teatro a ciascun docente di Lettere per mantenere 18h piene e 30h esatte per classe.
    """
    if num_classes < 1:
        num_classes = 6

    theater_title = " (+ Teatro)" if with_theater else ""
    config = SchoolConfig(
        num_days=5,
        daily_hours=[6, 6, 6, 6, 6],
        school_name=f"Scuola Secondaria di I Grado 'Dante Alighieri' ({num_classes} Classi)" + (" (DADA)" if is_dada else "") + theater_title,
        school_type="Secondaria I Grado (Scuola Media)",
        is_dada=is_dada,
        dada_prefer_double_hours=True,
        second_language=second_lang,
        subject_block_preferences={
            "art": True, "tec": True, "mot": True, "mus": True, "spa": True, "ita": True, "mat": True,
            "ing": False, "sci": False, "sto": False, "geo": False, "rel": False, "tea": False
        }
    )
    if with_theater:
        config.approfondimento_subject = "tea"
        config.approfondimento_type = "custom_activity"
        config.approfondimento_name = "Laboratorio di Teatro"
        config.approfondimento_deduct_from = "ita"

    # 1. Materie Ministeriali Scuola Media
    subjects = {
        "ita": Subject(id="ita", name="Italiano", color="#e74c3c", cdc="A-22"),
        "sto": Subject(id="sto", name="Storia", color="#e67e22", cdc="A-22"),
        "geo": Subject(id="geo", name="Geografia", color="#d35400", cdc="A-22"),
        "mat": Subject(id="mat", name="Matematica", color="#2980b9", cdc="A-28"),
        "sci": Subject(id="sci", name="Scienze", color="#27ae60", cdc="A-28"),
        "ing": Subject(id="ing", name="Inglese", color="#8e44ad", cdc="A-24"),
        "spa": Subject(id="spa", name=f"Seconda Lingua ({second_lang})", color="#9b59b6", cdc="A-24"),
        "tec": Subject(id="tec", name="Tecnologia", color="#16a085", cdc="A-60"),
        "mus": Subject(id="mus", name="Musica", color="#f39c12", cdc="A-30"),
        "art": Subject(id="art", name="Arte e Immagine", color="#e84393", cdc="A-01"),
        "mot": Subject(id="mot", name="Scienze Motorie", color="#00b894", cdc="A-48"),
        "rel": Subject(id="rel", name="Religione", color="#7f8c8d", cdc="Religione")
    }

    if with_theater:
        subjects["tea"] = Subject(id="tea", name="Laboratorio di Teatro", color="#8e44ad", cdc="A-22 / Potenziamento")

    # 2. Generazione Classi (1A, 2A, 3A, 1B, 2B, 3B, 1C, 2C, 3C...)
    classes = {}
    sections = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "L", "M", "N"]
    class_keys = []
    
    sec_idx = 0
    grade_idx = 1
    for i in range(num_classes):
        sec_letter = sections[sec_idx]
        c_id = f"{grade_idx}{sec_letter}"
        c_name = f"{grade_idx}ª {sec_letter}"
        classes[c_id] = SchoolClass(id=c_id, name=c_name, grade=grade_idx, section=sec_letter)
        class_keys.append(c_id)
        
        grade_idx += 1
        if grade_idx > 3:
            grade_idx = 1
            sec_idx = (sec_idx + 1) % len(sections)

    # 3. Generazione Aule della Scuola
    # Verranno collegate ai docenti dopo la creazione dell'organico docenti
    rooms = {}

    # 4. Generazione Cattedre e Assegnazioni Docenti
    teachers: Dict[str, Teacher] = {}
    assignments: List[TeachingAssignment] = []
    
    name_pointer = 0
    def next_teacher_name(subject_label: str) -> str:
        nonlocal name_pointer
        base_n = TEACHER_NAMES[name_pointer % len(TEACHER_NAMES)]
        name_pointer += 1
        return f"{base_n} ({subject_label})"

    # Helper per creare e registrare un docente con carico orario e desiderata personali
    def create_and_add_teacher(
        t_id: str, 
        name: str, 
        cdc: str, 
        hours: int, 
        is_pt: bool = False, 
        max_days: Optional[int] = None, 
        free_days: Optional[List[str]] = None, 
        late: bool = False, 
        early: bool = False, 
        late_days: Optional[List[str]] = None,
        early_days: Optional[List[str]] = None,
        unavail_slots: Optional[List[List[int]]] = None,
        soft_slots: Optional[List[List[int]]] = None
    ) -> Teacher:
        f_list = free_days or []
        t = Teacher(
            id=t_id,
            name=name,
            cdc=cdc,
            is_part_time=is_pt,
            contract_hours=hours,
            max_working_days=max_days if is_pt else 5,
            free_days=f_list,
            free_day_1=f_list[0] if len(f_list) > 0 else None,
            free_day_2=f_list[1] if len(f_list) > 1 else None,
            prefer_late_entry=late,
            prefer_early_exit=early,
            late_entry_days=late_days or [],
            early_exit_days=early_days or [],
            unavailable_slots=unavail_slots or [],
            soft_avoid_slots=soft_slots or [],
            max_daily_hours=5,
            max_consecutive_hours=4,
            max_gap_hours=2 if not is_pt else 1,
            prefer_compact_schedule=True
        )
        teachers[t_id] = t
        return t

    # A. LETTERE (A-22): 10h per classe (Standard: Ita 6h, Sto 2h, Geo 2h | Con Teatro: Ita 5h, Teatro 1h, Sto 2h, Geo 2h)
    let_teachers_assigned = []
    remaining_by_class = {}
    for c_id in class_keys:
        if with_theater:
            remaining_by_class[c_id] = [
                (c_id, "ita", 5, True),
                (c_id, "tea", 1, False),
                (c_id, "sto", 2, False),
                (c_id, "geo", 2, False)
            ]
        else:
            remaining_by_class[c_id] = [
                (c_id, "ita", 6, True),
                (c_id, "sto", 2, False),
                (c_id, "geo", 2, False)
            ]

    for c_idx in range(0, len(class_keys), 2):
        c1 = class_keys[c_idx]
        c2 = class_keys[c_idx + 1] if c_idx + 1 < len(class_keys) else None
        if c2:
            if with_theater:
                # c1: ita 5h, tea 1h, sto 2h, geo 2h (tot 10h)
                # c2: ita 5h, tea 1h, sto 2h (tot 8h)
                # Totale per il docente di cattedra = 18h (con 2h di Teatro totali!)
                t1_items = remaining_by_class[c1][:] + remaining_by_class[c2][:3]
                let_teachers_assigned.append(t1_items)
                remaining_by_class[c2] = remaining_by_class[c2][3:] # rimane [geo 2h]
            else:
                t1_items = remaining_by_class[c1][:] + [remaining_by_class[c2][0], remaining_by_class[c2][1]]
                let_teachers_assigned.append(t1_items)
                remaining_by_class[c2] = [remaining_by_class[c2][2]]
        else:
            t_items = remaining_by_class[c1][:]
            let_teachers_assigned.append(t_items)

    geo_residues = []
    for c_id in class_keys:
        if len(remaining_by_class[c_id]) == 1:
            geo_residues.append(remaining_by_class[c_id][0])

    # Se ci sono residui di geografia, dividili tra cattedre piene e spezzoni/part-time
    if len(geo_residues) >= 9:
        let_teachers_assigned.append(geo_residues[:5]) # 10h Part-Time Lettere
        let_teachers_assigned.append(geo_residues[5:9]) # 8h Part-Time Lettere
        geo_residues = geo_residues[9:]
    while geo_residues:
        chunk = geo_residues[:9]
        let_teachers_assigned.append(chunk)
        geo_residues = geo_residues[9:]

    for let_t_idx, t_items in enumerate(let_teachers_assigned, 1):
        tot_t_h = sum(x[2] for x in t_items)
        is_pt = (tot_t_h < 18)
        t_id = f"doc_let_{let_t_idx}"
        
        # Desiderata realistici diversificati per ciascun docente di Lettere
        if is_pt:
            t_name = next_teacher_name(f"Part-Time Lettere {tot_t_h}h")
            m_days = 3
            pt_free = ["Lunedì", "Mercoledì"] if tot_t_h >= 10 else ["Martedì", "Giovedì"]
            create_and_add_teacher(
                t_id, t_name, "A-22", tot_t_h, 
                is_pt=True, 
                max_days=m_days,
                free_days=pt_free,
                late=(let_t_idx % 2 == 0)
            )
        else:
            t_name = next_teacher_name("Lettere")
            # Docenti a tempo pieno con desiderata specifici
            free_choice = ["Lunedì", "Venerdì", "Mercoledì", "Giovedì"][let_t_idx % 4] if (config.num_days == 6) else None
            late_choice = ["Lunedì", "Giovedì"] if (let_t_idx % 3 == 0) else []
            early_choice = ["Mercoledì", "Venerdì"] if (let_t_idx % 3 == 1) else []
            unavail = [[0, 0], [0, 1]] if (let_t_idx == 2) else []
            soft_slots = [[2, 5], [4, 5]] if (let_t_idx % 2 == 0) else []
            create_and_add_teacher(
                t_id, t_name, "A-22", 18, 
                is_pt=False,
                free_days=[free_choice] if free_choice else [],
                late=(len(late_choice) > 0),
                early=(len(early_choice) > 0),
                late_days=late_choice,
                early_days=early_choice,
                unavail_slots=unavail,
                soft_slots=soft_slots
            )

        for it_c, it_s, it_h, it_d in t_items:
            f_dbl = config.subject_block_preferences.get(it_s, it_d)
            assignments.append(TeachingAssignment(
                id=f"a_{it_c}_{it_s}_{t_id}_{len(assignments)}".lower(),
                teacher_id=t_id,
                class_id=it_c,
                subject_id=it_s,
                hours_per_week=it_h,
                force_double_hours=f_dbl and (it_h >= 2),
                max_daily_hours=2 if (f_dbl and it_h >= 2) else 1
            ))

    # B. MATEMATICA E SCIENZE (A-28): 6h per classe (Mat 4h, Sci 2h)
    mat_pool = []
    for c_id in class_keys:
        mat_pool.append((c_id, "mat", 4, True))
        mat_pool.append((c_id, "sci", 2, False))

    mat_t_idx = 1
    current_mat_items = []
    current_mat_h = 0
    
    # Crea docenti a tempo pieno e almeno un docente Part-Time in Mat/Scienze (12h + 6h)
    target_cuts = [18] * (len(class_keys) // 3)
    if len(class_keys) >= 6 and len(target_cuts) >= 2:
        # Trasforma l'ultima cattedra da 18h in due part-time: 12h + 6h
        target_cuts[-1] = 12
        target_cuts.append(6)

    cut_idx = 0
    for item in mat_pool:
        current_mat_items.append(item)
        current_mat_h += item[2]
        cur_target = target_cuts[cut_idx] if cut_idx < len(target_cuts) else 18
        
        if current_mat_h >= cur_target:
            t_id = f"doc_mat_{mat_t_idx}"
            is_pt = (current_mat_h < 18)
            t_name = next_teacher_name("Mat/Scienze" if not is_pt else f"Part-Time Mat/Sci {current_mat_h}h")
            m_days = 2 if current_mat_h <= 6 else (3 if current_mat_h <= 12 else 5)
            
            if is_pt:
                pt_free = ["Lunedì", "Mercoledì"] if current_mat_h >= 12 else ["Martedì", "Giovedì"]
                create_and_add_teacher(
                    t_id, t_name, "A-28", current_mat_h, 
                    is_pt=True, 
                    max_days=3,
                    free_days=pt_free,
                    late_days=["Giovedì"]
                )
            else:
                free_choice = ["Venerdì", "Lunedì", "Mercoledì"][mat_t_idx % 3] if (config.num_days == 6) else None
                create_and_add_teacher(
                    t_id, t_name, "A-28", 18, 
                    is_pt=False,
                    free_days=[free_choice] if free_choice else [],
                    late=(mat_t_idx % 2 == 0),
                    early=(mat_t_idx % 3 == 0),
                    late_days=["Lunedì"] if (mat_t_idx % 2 == 0) else [],
                    early_days=["Venerdì"] if (mat_t_idx % 3 == 0) else []
                )
                
            for it_c, it_s, it_h, it_d in current_mat_items:
                f_dbl = config.subject_block_preferences.get(it_s, it_d)
                assignments.append(TeachingAssignment(
                    id=f"a_{it_c}_{it_s}_{t_id}_{len(assignments)}".lower(),
                    teacher_id=t_id,
                    class_id=it_c,
                    subject_id=it_s,
                    hours_per_week=it_h,
                    force_double_hours=f_dbl and (it_h >= 2),
                    max_daily_hours=2 if (f_dbl and it_h >= 2) else 1
                ))
            mat_t_idx += 1
            cut_idx += 1
            current_mat_items = []
            current_mat_h = 0

    if current_mat_items:
        t_id = f"doc_mat_{mat_t_idx}"
        is_pt = (current_mat_h < 18)
        t_name = next_teacher_name("Mat/Scienze" if not is_pt else f"Part-Time Mat/Sci {current_mat_h}h")
        m_days = 2 if current_mat_h <= 6 else (3 if current_mat_h <= 12 else 5)
        create_and_add_teacher(
            t_id, t_name, "A-28", current_mat_h, 
            is_pt=is_pt, 
            max_days=m_days,
            free_days=["Lunedì", "Mercoledì"] if is_pt else [],
            late_days=["Giovedì"] if is_pt else []
        )
        for it_c, it_s, it_h, it_d in current_mat_items:
            f_dbl = config.subject_block_preferences.get(it_s, it_d)
            assignments.append(TeachingAssignment(
                id=f"a_{it_c}_{it_s}_{t_id}_{len(assignments)}".lower(),
                teacher_id=t_id,
                class_id=it_c,
                subject_id=it_s,
                hours_per_week=it_h,
                force_double_hours=f_dbl and (it_h >= 2),
                max_daily_hours=2 if (f_dbl and it_h >= 2) else 1
            ))
        mat_t_idx += 1

    # C. INGLESE (A-24): 3h per classe
    ing_t_idx = 1
    # C. INGLESE (A-24): 3h per classe. 6 classi = 18h piena cattedra!
    ing_t_idx = 1
    current_ing_classes = []
    
    for c_id in class_keys:
        current_ing_classes.append(c_id)
        if len(current_ing_classes) == 6:
            t_id = f"doc_ing_{ing_t_idx}"
            t_name = next_teacher_name("Inglese")
            free_choice = ["Mercoledì", "Venerdì", "Lunedì"][ing_t_idx % 3] if (config.num_days == 6) else None
            late_choice = ["Lunedì"] if (ing_t_idx == 2) else []
            early_choice = ["Venerdì"] if (ing_t_idx == 1) else []
            create_and_add_teacher(
                t_id, t_name, "A-24", 18,
                is_pt=False,
                free_days=[free_choice] if free_choice else [],
                late=(len(late_choice) > 0),
                early=(len(early_choice) > 0),
                late_days=late_choice,
                early_days=early_choice
            )
            for c_k in current_ing_classes:
                assignments.append(TeachingAssignment(
                    id=f"a_{c_k}_ing_{t_id}_{len(assignments)}".lower(),
                    teacher_id=t_id,
                    class_id=c_k,
                    subject_id="ing",
                    hours_per_week=3,
                    force_double_hours=False,
                    max_daily_hours=2
                ))
            ing_t_idx += 1
            current_ing_classes = []

    if current_ing_classes:
        h_rem = len(current_ing_classes) * 3
        t_id = f"doc_ing_{ing_t_idx}"
        is_pt = (h_rem < 18)
        t_name = next_teacher_name("Inglese" if not is_pt else f"Part-Time Inglese {h_rem}h")
        m_days = 2 if h_rem <= 6 else (3 if h_rem <= 12 else 5)
        create_and_add_teacher(
            t_id, t_name, "A-24", h_rem,
            is_pt=is_pt,
            max_days=m_days,
            free_days=["Lunedì", "Mercoledì"] if is_pt else [],
            late=True
        )
        for c_k in current_ing_classes:
            assignments.append(TeachingAssignment(
                id=f"a_{c_k}_ing_{t_id}_{len(assignments)}".lower(),
                teacher_id=t_id,
                class_id=c_k,
                subject_id="ing",
                hours_per_week=3,
                force_double_hours=False,
                max_daily_hours=2
            ))
        ing_t_idx += 1

    # D. DISCIPLINE DA 2h (Seconda Lingua, Tecnologia, Musica, Arte, Motoria)
    spec_subjects = [
        ("spa", second_lang, "A-24", True),
        ("tec", "Tecnologia", "A-60", True),
        ("mus", "Musica", "A-30", True),
        ("art", "Arte", "A-01", True),
        ("mot", "Motoria", "A-48", True),
    ]

    for s_idx, (s_code, s_label, s_cdc, s_force_dbl) in enumerate(spec_subjects, 1):
        t_idx = 1
        current_sub_classes = []
        
        for c_id in class_keys:
            current_sub_classes.append(c_id)
            if len(current_sub_classes) == 9: # 9 classi * 2h = 18h piena cattedra!
                t_id = f"doc_{s_code}_{t_idx}"
                t_name = next_teacher_name(s_label)
                # Desiderata personali per docenti specialisti
                late_choice = ["Lunedì"] if (t_idx % 2 == 0) else []
                early_choice = ["Venerdì"] if (t_idx % 2 == 1) else []
                soft_slots = [[0, 0]] if (s_idx % 2 == 1) else []
                free_choice = ["Giovedì", "Lunedì", "Martedì", "Venerdì", "Mercoledì"][(s_idx + t_idx) % 5] if (config.num_days == 6) else None
                
                create_and_add_teacher(
                    t_id, t_name, s_cdc, 18,
                    is_pt=False,
                    free_days=[free_choice] if free_choice else [],
                    late=(len(late_choice) > 0),
                    early=(len(early_choice) > 0),
                    late_days=late_choice,
                    early_days=early_choice,
                    soft_slots=soft_slots
                )
                for c_k in current_sub_classes:
                    f_dbl = bool(s_force_dbl)
                    assignments.append(TeachingAssignment(
                        id=f"a_{c_k}_{s_code}_{t_id}_{len(assignments)}".lower(),
                        teacher_id=t_id,
                        class_id=c_k,
                        subject_id=s_code,
                        hours_per_week=2,
                        force_double_hours=f_dbl or is_dada,
                        max_daily_hours=2 if f_dbl else 1
                    ))
                current_sub_classes = []
                t_idx += 1

        if current_sub_classes:
            h_rem = len(current_sub_classes) * 2
            t_id = f"doc_{s_code}_{t_idx}"
            is_pt = (h_rem < 18)
            t_name = next_teacher_name(s_label if not is_pt else f"Part-Time {s_label} {h_rem}h")
            m_days = 2 if h_rem <= 8 else (3 if h_rem <= 12 else 5)
            create_and_add_teacher(
                t_id, t_name, s_cdc, h_rem,
                is_pt=is_pt,
                max_days=m_days,
                free_days=["Lunedì", "Mercoledì"] if is_pt else [],
                late=(t_idx % 2 == 1)
            )
            for c_k in current_sub_classes:
                f_dbl = bool(s_force_dbl)
                assignments.append(TeachingAssignment(
                    id=f"a_{c_k}_{s_code}_{t_id}_{len(assignments)}".lower(),
                    teacher_id=t_id,
                    class_id=c_k,
                    subject_id=s_code,
                    hours_per_week=2,
                    force_double_hours=f_dbl or is_dada,
                    max_daily_hours=2 if f_dbl else 1
                ))
            t_idx += 1

    # E. RELIGIONE: 1h per classe (es. divisa in Part-Time 12h + 6h)
    rel_t_idx = 1
    current_rel_classes = []
    target_rel_cuts = [12, 6] if len(class_keys) == 18 else [18] * (len(class_keys) // 18 or 1)
    cut_rel_idx = 0
    
    for c_id in class_keys:
        current_rel_classes.append(c_id)
        cur_req_h = len(current_rel_classes) * 1
        cur_target = target_rel_cuts[cut_rel_idx] if cut_rel_idx < len(target_rel_cuts) else 18
        
        if cur_req_h >= cur_target:
            t_id = f"doc_rel_{rel_t_idx}"
            is_pt = (cur_req_h < 18)
            t_name = next_teacher_name("Religione" if not is_pt else f"Part-Time Religione {cur_req_h}h")
            m_days = 2 if cur_req_h <= 6 else (3 if cur_req_h <= 12 else 4)
            create_and_add_teacher(
                t_id, t_name, "Religione", cur_req_h,
                is_pt=is_pt,
                max_days=m_days,
                free_days=["Giovedì", "Venerdì"] if cur_req_h >= 12 else ["Lunedì", "Martedì", "Mercoledì"],
                late=True
            )
            for c_k in current_rel_classes:
                assignments.append(TeachingAssignment(
                    id=f"a_{c_k}_rel_{t_id}_{len(assignments)}".lower(),
                    teacher_id=t_id,
                    class_id=c_k,
                    subject_id="rel",
                    hours_per_week=1,
                    force_double_hours=False,
                    max_daily_hours=1
                ))
            rel_t_idx += 1
            cut_rel_idx += 1
            current_rel_classes = []

    if current_rel_classes:
        cur_req_h = len(current_rel_classes) * 1
        t_id = f"doc_rel_{rel_t_idx}"
        is_pt = (cur_req_h < 18)
        t_name = next_teacher_name("Religione" if not is_pt else f"Part-Time Religione {cur_req_h}h")
        m_days = 2 if cur_req_h <= 6 else (3 if cur_req_h <= 12 else 4)
        create_and_add_teacher(
            t_id, t_name, "Religione", cur_req_h,
            is_pt=is_pt,
            max_days=m_days,
            free_days=["Martedì", "Giovedì", "Venerdì"] if is_pt else [],
            late=True
        )
        for c_k in current_rel_classes:
            assignments.append(TeachingAssignment(
                id=f"a_{c_k}_rel_{t_id}_{len(assignments)}".lower(),
                teacher_id=t_id,
                class_id=c_k,
                subject_id="rel",
                hours_per_week=1,
                force_double_hours=False,
                max_daily_hours=1
            ))
        rel_t_idx += 1

    # 5. Generazione Aule della Scuola con Assegnazione Docenti
    if is_dada:
        # Modello DADA: Aule tematiche disciplinari con docenti assegnati (100% garantiti)
        rooms = {
            # Lettere (A-22): 1 aula dedicata a Priorità 1 per ciascun docente di cattedra
            "chichibio": Classroom(id="chichibio", name="CHICHIBIO (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_1"] if "doc_let_1" in teachers else []),
            "magellano": Classroom(id="magellano", name="MAGELLANO (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_2"] if "doc_let_2" in teachers else []),
            "dante": Classroom(id="dante", name="DANTE (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_3"] if "doc_let_3" in teachers else []),
            "antigone": Classroom(id="antigone", name="ANTIGONE (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_4"] if "doc_let_4" in teachers else []),
            "pinocchio": Classroom(id="pinocchio", name="PINOCCHIO (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_5"] if "doc_let_5" in teachers else []),
            "leopardi": Classroom(id="leopardi", name="LEOPARDI (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_6"] if "doc_let_6" in teachers else []),
            "didone": Classroom(id="didone", name="DIDONE (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_7"] if "doc_let_7" in teachers else []),
            "marco_polo": Classroom(id="marco_polo", name="MARCO POLO (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_8"] if "doc_let_8" in teachers else []),
            "gagarin": Classroom(id="gagarin", name="GAGARIN (Aula Lettere)", subject_ids=["ita", "sto", "geo"], capacity=1, priority=1, teacher_ids=["doc_let_9"] if "doc_let_9" in teachers else []),

            # Matematica e Scienze (A-28): 1 aula/lab a Priorità 1 per ciascun docente di cattedra
            "euclide": Classroom(id="euclide", name="EUCLIDE (Aula Matematica)", subject_ids=["mat", "sci"], capacity=1, priority=1, teacher_ids=["doc_mat_1"] if "doc_mat_1" in teachers else []),
            "pitagora": Classroom(id="pitagora", name="PITAGORA (Aula Matematica)", subject_ids=["mat", "sci"], capacity=1, priority=1, teacher_ids=["doc_mat_2"] if "doc_mat_2" in teachers else []),
            "galileo": Classroom(id="galileo", name="GALILEO (Lab Scienze & Matematica)", subject_ids=["sci", "mat"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_mat_3"] if "doc_mat_3" in teachers else []),
            "eulero": Classroom(id="eulero", name="EULERO (Aula Matematica)", subject_ids=["mat", "sci"], capacity=1, priority=1, teacher_ids=["doc_mat_4"] if "doc_mat_4" in teachers else []),
            "newton": Classroom(id="newton", name="NEWTON (Aula Matematica)", subject_ids=["mat", "sci"], capacity=1, priority=1, teacher_ids=["doc_mat_5"] if "doc_mat_5" in teachers else []),

            # Lingue Straniere: 1 aula a Priorità 1 per ciascun docente di lingua
            "queen": Classroom(id="queen", name="QUEEN (Aula Inglese)", subject_ids=["ing"], capacity=1, priority=1, teacher_ids=["doc_ing_1"] if "doc_ing_1" in teachers else []),
            "strawberry": Classroom(id="strawberry", name="STRAWBERRY (Aula Inglese)", subject_ids=["ing"], capacity=1, priority=1, teacher_ids=["doc_ing_2"] if "doc_ing_2" in teachers else []),
            "verne": Classroom(id="verne", name="VERNE (Aula Seconda Lingua)", subject_ids=["spa"], capacity=1, priority=1, teacher_ids=["doc_spa_1"] if "doc_spa_1" in teachers else []),
            "moliere": Classroom(id="moliere", name="MOLIERE (Aula Seconda Lingua)", subject_ids=["spa"], capacity=1, priority=1, teacher_ids=["doc_spa_2"] if "doc_spa_2" in teachers else []),

            # Scienze Motorie: BEBE VIO Principale (Priorità 1 - Satura a 30h) vs MURATORI (Priorità 2 - Solo per le restanti 6h)
            "bebe_vio": Classroom(id="bebe_vio", name="BEBE VIO (Palestra Principale)", subject_ids=["mot"], capacity=1, is_special_lab=True, priority=1),
            "palestra_muratori": Classroom(id="palestra_muratori", name="PALESTRA MURATORI (Secondaria / Emergenza)", subject_ids=["mot"], capacity=1, is_special_lab=True, priority=2),

            # Laboratori Artistici & Tecnologici: 1 lab a Priorità 1 per ciascun docente
            "monet": Classroom(id="monet", name="MONET (Lab Arte Principale)", subject_ids=["art"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_art_1"] if "doc_art_1" in teachers else []),
            "miro": Classroom(id="miro", name="MIRO' (Lab Arte)", subject_ids=["art"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_art_2"] if "doc_art_2" in teachers else []),
            "archimede": Classroom(id="archimede", name="ARCHIMEDE (Lab Tecnologia Principale)", subject_ids=["tec"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_tec_1"] if "doc_tec_1" in teachers else []),
            "leonardo": Classroom(id="leonardo", name="LEONARDO (Lab Tecnologia)", subject_ids=["tec"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_tec_2"] if "doc_tec_2" in teachers else []),
            "r2_d2": Classroom(id="r2_d2", name="R2-D2 (Lab STEM / Robotica)", subject_ids=["tec"], capacity=1, is_special_lab=True, priority=2),

            # Laboratori Musicali: 1 lab a Priorità 1 per ciascun docente
            "bach": Classroom(id="bach", name="BACH (Lab Musica Principale)", subject_ids=["mus"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_mus_1"] if "doc_mus_1" in teachers else []),
            "armstrong": Classroom(id="armstrong", name="ARMSTRONG (Lab Musica)", subject_ids=["mus"], capacity=1, is_special_lab=True, priority=1, teacher_ids=["doc_mus_2"] if "doc_mus_2" in teachers else []),

            # Religione & Spazi Teatrali:
            "maddalena_malala": Classroom(id="maddalena_malala", name="MADDALENA-MALALA (Religione)", subject_ids=["rel"], capacity=1, priority=1, teacher_ids=["doc_rel_1"] if "doc_rel_1" in teachers else []),
            "teatro": Classroom(id="teatro", name="LABORATORIO TEATRO (Spazio Principale)", subject_ids=["tea", "app_custom"], capacity=1, is_special_lab=True, priority=1),
            "auditorium": Classroom(id="auditorium", name="AUDITORIUM (Spazio Secondario / Riserva)", subject_ids=["tea", "app_custom"], capacity=1, is_special_lab=True, priority=2),
        }
    else:
        # Modello Tradizionale: Aule ordinarie per TUTTE le classi della scuola + Palestre e Laboratori Speciali Condivisi
        rooms = {}
        for c_id, c_obj in classes.items():
            rooms[f"aula_{c_id.lower()}"] = Classroom(
                id=f"aula_{c_id.lower()}",
                name=f"Aula {c_obj.name}",
                subject_ids=[],
                capacity=1,
                is_special_lab=False,
                priority=1
            )
        rooms["bebe_vio"] = Classroom(id="bebe_vio", name="Palestra BEBE VIO (Principale)", subject_ids=["mot"], capacity=1, is_special_lab=True, priority=1)
        rooms["palestra_muratori"] = Classroom(id="palestra_muratori", name="Palestra MURATORI (Secondaria / Emergenza)", subject_ids=["mot"], capacity=1, is_special_lab=True, priority=2)
        rooms["lab_arte"] = Classroom(id="lab_arte", name="Laboratorio di Arte (Principale)", subject_ids=["art"], capacity=1, is_special_lab=True, priority=1)
        rooms["lab_arte_2"] = Classroom(id="lab_arte_2", name="Laboratorio di Arte (Secondario)", subject_ids=["art"], capacity=1, is_special_lab=True, priority=2)
        rooms["lab_informatica"] = Classroom(id="lab_informatica", name="Laboratorio di Informatica (Principale)", subject_ids=["tec"], capacity=1, is_special_lab=True, priority=1)
        rooms["lab_informatica_2"] = Classroom(id="lab_informatica_2", name="Laboratorio di Informatica (Secondario)", subject_ids=["tec"], capacity=1, is_special_lab=True, priority=2)
        rooms["lab_musica"] = Classroom(id="lab_musica", name="Laboratorio di Musica (Principale)", subject_ids=["mus"], capacity=1, is_special_lab=True, priority=1)
        rooms["lab_musica_2"] = Classroom(id="lab_musica_2", name="Laboratorio di Musica (Secondario)", subject_ids=["mus"], capacity=1, is_special_lab=True, priority=2)
        rooms["lab_scienze"] = Classroom(id="lab_scienze", name="Laboratorio di Scienze (Principale)", subject_ids=["sci"], capacity=1, is_special_lab=True, priority=1)
        rooms["lab_scienze_2"] = Classroom(id="lab_scienze_2", name="Laboratorio di Scienze (Secondario)", subject_ids=["sci"], capacity=1, is_special_lab=True, priority=2)
        if with_theater:
            rooms["teatro"] = Classroom(id="teatro", name="Laboratorio di Teatro (Spazio Principale)", subject_ids=["tea", "app_custom"], capacity=1, is_special_lab=True, priority=1)
            rooms["auditorium"] = Classroom(id="auditorium", name="Auditorium (Spazio Secondario)", subject_ids=["tea", "app_custom"], capacity=1, is_special_lab=True, priority=2)

    return TimetableProblem(
        config=config,
        teachers=teachers,
        classes=classes,
        subjects=subjects,
        rooms=rooms,
        assignments=assignments
    )

def get_empty_problem(school_name: str = "Scuola Secondaria di I Grado", num_days: int = 5) -> TimetableProblem:
    """Genera una struttura orario completamente vuota (0 docenti, 0 classi, 0 cattedre) con le discipline standard."""
    config = SchoolConfig(
        num_days=num_days,
        daily_hours=[6] * num_days,
        school_name=school_name,
        school_type="Secondaria I Grado (Scuola Media)",
        is_dada=False,
        second_language="Spagnolo"
    )
    subjects = {
        "ita": Subject(id="ita", name="Italiano", cdc="A-22", color="#e74c3c"),
        "sto": Subject(id="sto", name="Storia", cdc="A-22", color="#e67e22"),
        "geo": Subject(id="geo", name="Geografia", cdc="A-22", color="#f39c12"),
        "mat": Subject(id="mat", name="Matematica", cdc="A-28", color="#2980b9"),
        "sci": Subject(id="sci", name="Scienze", cdc="A-28", color="#27ae60"),
        "ing": Subject(id="ing", name="Inglese", cdc="AB25", color="#8e44ad"),
        "spa": Subject(id="spa", name="Spagnolo", cdc="AA25", color="#d35400"),
        "tec": Subject(id="tec", name="Tecnologia", cdc="A-60", color="#16a085"),
        "art": Subject(id="art", name="Arte e Immagine", cdc="A-01", color="#e84393"),
        "mus": Subject(id="mus", name="Musica", cdc="A-30", color="#0984e3"),
        "mot": Subject(id="mot", name="Scienze Motorie", cdc="A-49", color="#00b894"),
        "rel": Subject(id="rel", name="Religione Cattolica", cdc="RC", color="#6c5ce7"),
        "app": Subject(id="app", name="Approfondimento / Potenziamento", cdc="A-22", color="#fd79a8")
    }
    return TimetableProblem(
        config=config,
        teachers={},
        classes={},
        subjects=subjects,
        rooms={},
        assignments=[]
    )
