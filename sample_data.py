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
    TeachingAssignment, TimetableProblem, DAYS_OF_WEEK,
    StudentDVA, SupportAssignment, EnhancementAssignment
)

# Docenti ufficiali assegnati agli spazi DADA della scuola (Nomi di Fantasia)
OFFICIAL_TEACHERS_BY_CDC = {
    "let": [
        ("doc_let_1", "Prof. Valenti S.", "A-22"),
        ("doc_let_2", "Prof.ssa Montanari G.", "A-22"),
        ("doc_let_3", "Prof. De Angelis S.", "A-22"),
        ("doc_let_4", "Prof.ssa Rinaldi B.", "A-22"),
        ("doc_let_5", "Prof. Silvestri M.", "A-22"),
        ("doc_let_6", "Prof.ssa Lombardi S.", "A-22"),
        ("doc_let_7", "Prof.ssa Costantini B.", "A-22"),
        ("doc_let_8", "Prof. Barbieri E.", "A-22"),
        ("doc_let_9", "Prof.ssa Ferri F.", "A-22"),
        ("doc_let_10", "Prof. Pellegrino D.", "A-22"),
        ("doc_let_11", "Prof. Damico S.", "A-22"),
    ],
    "mat": [
        ("doc_mat_1", "Prof. Marchetti E.", "A-28"),
        ("doc_mat_2", "Prof. Serra G.", "A-28"),
        ("doc_mat_3", "Prof. Galli S.", "A-28"),
        ("doc_mat_4", "Prof. Donati E.", "A-28"),
        ("doc_mat_5", "Prof. Bernardi B.", "A-28"),
        ("doc_mat_6", "Prof. Fontana R.", "A-28"),
        ("doc_mat_7", "Prof.ssa Villa E.", "A-28"),
    ],
    "tec": [
        ("doc_tec_1", "Prof. Vitali R.", "A-60"),
        ("doc_tec_2", "Prof. Mariani A.", "A-60"),
    ],
    "ing": [
        ("doc_ing_1", "Prof. Sartori S.", "A-24"),
        ("doc_ing_2", "Prof.ssa Colombo E.", "A-24"),
        ("doc_ing_3", "Prof. Caruso F.", "A-24"),
    ],
    "spa": [
        ("doc_spa_1", "Prof. Moretti A.", "A-24"),
        ("doc_spa_2", "Prof. Battaglia R.", "A-24"),
    ],
    "art": [
        ("doc_art_1", "Prof. Grassi F.", "A-01"),
        ("doc_art_2", "Prof.ssa Fiore E.", "A-01"),
        ("doc_art_3", "Prof. Pagano I.", "A-01"),
    ],
    "mus": [
        ("doc_mus_1", "Prof. Bellini A.", "A-30"),
        ("doc_mus_2", "Prof. Gentile G.", "A-30"),
    ],
    "mot": [
        ("doc_mot_1", "Prof.ssa Rossetti M.", "A-48"),
        ("doc_mot_2", "Prof.ssa Leone P.", "A-48"),
        ("doc_mot_3", "Prof. Valentini S.", "A-48"),
        ("doc_mot_4", "Prof. Parisi D.", "A-48"),
    ],
    "rel": [
        ("doc_rel_1", "Prof. De Rosa P.", "Religione"),
    ],
}

def get_official_teacher_meta(subj_code: str, idx: int) -> Tuple[str, str, str]:
    pool = OFFICIAL_TEACHERS_BY_CDC.get(subj_code, [])
    if 1 <= idx <= len(pool):
        return pool[idx - 1]
    return f"doc_{subj_code}_{idx}", f"Prof. Docente {subj_code.upper()} {idx}", pool[0][2] if pool else "Docente"

# Pool di cognomi realistici di riserva
TEACHER_NAMES = [
    "Prof.ssa Bianchi", "Prof. Romano", "Prof.ssa Marino", "Prof. Verdi",
    "Prof.ssa Ferrari", "Prof.ssa Rossi", "Prof. Russo", "Prof.ssa Ricci",
    "Prof. Conti", "Prof. De Luca", "Prof.ssa Fontana", "Prof.ssa Gallo",
    "Prof. Costa", "Prof.ssa Giordano", "Prof. Mancini", "Prof. Rizzo"
]

def get_sample_problem(
    num_classes: int = 18, 
    is_dada: bool = False, 
    second_lang: str = "Spagnolo", 
    with_theater: bool = False, 
    num_days: int = 5,
    with_musical_curriculum: bool = True,
    with_extended_curriculum: bool = False
) -> TimetableProblem:
    """
    Genera un problema realistico per una scuola media con `num_classes` classi (predefinito: 18 classi)
    su 5 o 6 giorni di lezione settimanali.
    Include supporto completo per:
    - Indirizzo Musicale (Corso F a 32h, Orchestra/Solfeggio con fino a 4 docenti in compresenza: Flauto, Violino, Chitarra, Clarinetto)
    - Tempo Prolungato (Corso E a 36h con rientri pomeridiani e compresenze)
    """
    if num_classes < 1:
        num_classes = 6

    theater_title = " (+ Teatro)" if with_theater else ""
    musical_title = " (+ Indirizzo Musicale 32h)" if with_musical_curriculum else ""
    extended_title = " (+ Tempo Prolungato 36h)" if with_extended_curriculum else ""
    days_title = " (Settimana 6 Giorni Lun-Sab)" if num_days == 6 else ""
    daily_h = [5, 5, 5, 5, 5, 5] if num_days == 6 else [6, 6, 6, 6, 6]
    
    config = SchoolConfig(
        num_days=num_days,
        daily_hours=daily_h,
        school_name=f"Scuola Secondaria di I Grado 'Dante Alighieri' ({num_classes} Classi)" + (" (DADA)" if is_dada else "") + theater_title + musical_title + extended_title + days_title,
        school_type="Secondaria I Grado (Scuola Media)",
        is_dada=is_dada,
        dada_prefer_double_hours=True,
        second_language=second_lang,
        has_musical_curriculum=with_musical_curriculum,
        musical_instruments=["Flauto", "Violino", "Chitarra", "Clarinetto"],
        musical_orchestra_co_teachers=4,
        default_lunch_break_duration=60,
        subject_block_preferences={
            "art": True, "tec": True, "mot": True, "mus": True, "spa": True, "ita": True, "mat": True,
            "orch": True, "solf": True, "ing": False, "sci": False, "sto": False, "geo": False, "rel": False, "tea": False
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

    if with_musical_curriculum:
        subjects["orch"] = Subject(id="orch", name="Musica d'Insieme (Orchestra)", color="#d97706", cdc="A-56 / A-30", is_musical_discipline=True, default_double_hours=True)
        subjects["solf"] = Subject(id="solf", name="Teoria e Solfeggio / Lettura", color="#b45309", cdc="A-56 / A-30", is_musical_discipline=True, default_double_hours=False)

    if with_extended_curriculum:
        subjects["lab_prol"] = Subject(id="lab_prol", name="Laboratorio / Compresenza Prolungato", color="#059669", cdc="A-22 / A-28", is_extended_time_discipline=True)

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
        
        curriculum = "ordinario"
        target_h = 30
        afternoons = []
        lunch_m = 60

        # Corso F: Indirizzo Musicale (32h con rientri pomeridiani personalizzati)
        if sec_letter == "F" and with_musical_curriculum:
            curriculum = "musicale"
            target_h = 32
            # Esempio: 1F al Lunedì, 2F al Martedì, 3F al Mercoledì oppure personalizzabili
            mus_afternoon_map = {1: ["Lunedì"], 2: ["Martedì"], 3: ["Mercoledì"]}
            afternoons = mus_afternoon_map.get(grade_idx, ["Lunedì"])
            lunch_m = 60

        # Corso E: Tempo Prolungato (36h con 2 pomeriggi)
        elif sec_letter == "E" and with_extended_curriculum:
            curriculum = "prolungato"
            target_h = 36
            afternoons = ["Martedì", "Giovedì"] # Di solito due pomeriggi
            lunch_m = 60

        classes[c_id] = SchoolClass(
            id=c_id, 
            name=c_name, 
            grade=grade_idx, 
            section=sec_letter,
            curriculum_type=curriculum,
            weekly_hours_target=target_h,
            afternoon_days=afternoons,
            lunch_break_duration=lunch_m
        )
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
        soft_slots: Optional[List[List[int]]] = None,
        preferred_areas: Optional[List[str]] = None
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
            preferred_areas=preferred_areas or [],
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
        t_id, official_t_name, _ = get_official_teacher_meta("let", let_t_idx)
        t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {tot_t_h}h)"
        
        # Desiderata realistici diversificati per ciascun docente di Lettere
        if is_pt:
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
            free_choice = ["Lunedì", "Sabato", "Mercoledì", "Giovedì", "Venerdì", "Martedì"][(let_t_idx - 1) % 6] if (config.num_days == 6) else None
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
        target_cuts[-1] = 12
        target_cuts.append(6)

    cut_idx = 0
    for item in mat_pool:
        current_mat_items.append(item)
        current_mat_h += item[2]
        cur_target = target_cuts[cut_idx] if cut_idx < len(target_cuts) else 18
        
        if current_mat_h >= cur_target:
            t_id, official_t_name, _ = get_official_teacher_meta("mat", mat_t_idx)
            is_pt = (current_mat_h < 18)
            t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {current_mat_h}h)"
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
                free_choice = ["Venerdì", "Lunedì", "Mercoledì", "Sabato", "Giovedì", "Martedì"][(mat_t_idx - 1) % 6] if (config.num_days == 6) else None
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
        t_id, official_t_name, _ = get_official_teacher_meta("mat", mat_t_idx)
        is_pt = (current_mat_h < 18)
        t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {current_mat_h}h)"
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
    current_ing_classes = []
    
    for c_id in class_keys:
        current_ing_classes.append(c_id)
        if len(current_ing_classes) == 6:
            t_id, official_t_name, _ = get_official_teacher_meta("ing", ing_t_idx)
            t_name = official_t_name
            free_choice = ["Mercoledì", "Sabato", "Lunedì", "Venerdì"][(ing_t_idx - 1) % 4] if (config.num_days == 6) else None
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
        t_id, official_t_name, _ = get_official_teacher_meta("ing", ing_t_idx)
        is_pt = (h_rem < 18)
        t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {h_rem}h)"
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
                t_id, official_t_name, _ = get_official_teacher_meta(s_code, t_idx)
                t_name = official_t_name
                # Desiderata personali per docenti specialisti (giorno libero su 6 giorni)
                late_choice = ["Lunedì"] if (t_idx % 2 == 0) else []
                early_choice = ["Venerdì"] if (t_idx % 2 == 1) else []
                soft_slots = [[0, 0]] if (s_idx % 2 == 1) else []
                free_choice = ["Giovedì", "Lunedì", "Martedì", "Venerdì", "Mercoledì", "Sabato"][(s_idx * 2 + t_idx) % 6] if (config.num_days == 6) else None
                
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
                        force_double_hours=f_dbl,
                        max_daily_hours=2 if f_dbl else 1
                    ))
                current_sub_classes = []
                t_idx += 1

        if current_sub_classes:
            h_rem = len(current_sub_classes) * 2
            t_id, official_t_name, _ = get_official_teacher_meta(s_code, t_idx)
            is_pt = (h_rem < 18)
            t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {h_rem}h)"
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
                    force_double_hours=f_dbl,
                    max_daily_hours=2
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
            t_id, official_t_name, _ = get_official_teacher_meta("rel", rel_t_idx)
            is_pt = (cur_req_h < 18)
            t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {cur_req_h}h)"
            m_days = 2 if cur_req_h <= 6 else (3 if cur_req_h <= 12 else 4)
            free_choice_rel = ["Sabato", "Lunedì"][(rel_t_idx - 1) % 2] if (config.num_days == 6) else None
            create_and_add_teacher(
                t_id, t_name, "Religione", cur_req_h,
                is_pt=is_pt,
                max_days=m_days,
                free_days=[free_choice_rel] if (free_choice_rel and not is_pt) else (["Giovedì", "Venerdì"] if cur_req_h >= 12 else ["Lunedì", "Martedì", "Mercoledì"]),
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
        t_id, official_t_name, _ = get_official_teacher_meta("rel", rel_t_idx)
        is_pt = (cur_req_h < 18)
        t_name = official_t_name if not is_pt else f"{official_t_name} (Part-Time {cur_req_h}h)"
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

    # F. INDIRIZZO MUSICALE (32h - Corso F): 4 Docenti di Strumento (Flauto, Violino, Chitarra, Clarinetto)
    # 2 ore per classe musicale (1F, 2F, 3F): Orchestra / Teoria con compresenza fino a 4 docenti
    if with_musical_curriculum:
        mus_classes = [c_id for c_id in class_keys if classes[c_id].curriculum_type == "musicale"]
        if mus_classes:
            # 4 Docenti di Strumento Musicale (A-56 / A-30)
            doc_flauto = create_and_add_teacher(
                "doc_str_flauto", "Prof.ssa Barbieri C. (Flauto)", "A-56 Strumento Musicale (Flauto)", 18,
                is_pt=False, max_days=5, late=False
            )
            doc_violino = create_and_add_teacher(
                "doc_str_violino", "Prof. Vitali E. (Violino)", "A-56 Strumento Musicale (Violino)", 18,
                is_pt=False, max_days=5, late=False
            )
            doc_chitarra = create_and_add_teacher(
                "doc_str_chitarra", "Prof.ssa Monti S. (Chitarra)", "A-56 Strumento Musicale (Chitarra)", 18,
                is_pt=False, max_days=5, late=False
            )
            doc_clarinetto = create_and_add_teacher(
                "doc_str_clarinetto", "Prof. De Luca M. (Clarinetto)", "A-56 Strumento Musicale (Clarinetto)", 18,
                is_pt=False, max_days=5, late=False
            )
            
            instrument_co_teachers = ["doc_str_violino", "doc_str_chitarra", "doc_str_clarinetto"]
            
            for c_mus in mus_classes:
                # 2 ore aggiuntive per classe: 2h di Orchestra / Musica d'Insieme (oppure 1h Orch + 1h Solfeggio)
                # con TUTTI E 4 I DOCENTI IN COMPRESENZA
                assignments.append(TeachingAssignment(
                    id=f"a_{c_mus}_orch_doc_str_flauto_{len(assignments)}".lower(),
                    teacher_id="doc_str_flauto",
                    class_id=c_mus,
                    subject_id="orch",
                    hours_per_week=2,
                    force_double_hours=True,
                    max_daily_hours=2,
                    co_teacher_ids=instrument_co_teachers,
                    preferred_room_id="auditorium"
                ))

    # G. TEMPO PROLUNGATO (36h - Corso E): 6 ore aggiuntive (Laboratori, Mensa, Compresenze Lettere/Matematica)
    if with_extended_curriculum:
        ext_classes = [c_id for c_id in class_keys if classes[c_id].curriculum_type == "prolungato"]
        if ext_classes:
            doc_prol = create_and_add_teacher(
                "doc_pot_prolungato", "Prof.ssa Rinaldi B. (Compresenze Prolungato)", "A-22 / A-28", 18,
                is_pt=False, max_days=5, late=False
            )
            for c_ext in ext_classes:
                assignments.append(TeachingAssignment(
                    id=f"a_{c_ext}_lab_prol_{len(assignments)}".lower(),
                    teacher_id="doc_pot_prolungato",
                    class_id=c_ext,
                    subject_id="lab_prol",
                    hours_per_week=6,
                    force_double_hours=True,
                    max_daily_hours=2
                ))

    # 5. Generazione Aule della Scuola con Assegnazione Docenti (DADA Ufficiale 26 Spazi)
    if is_dada:
        rooms = {
            "leonardo": Classroom(
                id="leonardo",
                name="LEONARDO",
                subject_ids=["tec", "sci"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_tec_1", "doc_mat_1", "doc_mat_6"] if t in teachers]
            ),
            "archimede": Classroom(
                id="archimede",
                name="ARCHIMEDE",
                subject_ids=["tec"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_tec_2"] if t in teachers]
            ),
            "magellano": Classroom(
                id="magellano",
                name="MAGELLANO",
                subject_ids=["sto", "geo"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_2", "doc_let_9", "doc_let_4", "doc_let_6"] if t in teachers]
            ),
            "bebe_vio": Classroom(
                id="bebe_vio",
                name="BEBE VIO",
                subject_ids=["mot"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_mot_1", "doc_mot_2", "doc_mot_3"] if t in teachers]
            ),
            "palestra_murato": Classroom(
                id="palestra_murato",
                name="PALESTRA MURATO",
                subject_ids=["mot"],
                capacity=1,
                is_special_lab=True,
                priority=2,
                teacher_ids=[t for t in ["doc_mot_4", "doc_mot_1"] if t in teachers]
            ),
            "galileo": Classroom(
                id="galileo",
                name="GALILEO",
                subject_ids=["sci"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_mat_7", "doc_mat_5", "doc_mat_2", "doc_mat_4", "doc_mat_3", "doc_mat_6"] if t in teachers]
            ),
            "maddalena_malal": Classroom(
                id="maddalena_malal",
                name="MADDALENA-MALAL",
                subject_ids=["rel"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_rel_1"] if t in teachers]
            ),
            "bach": Classroom(
                id="bach",
                name="BACH",
                subject_ids=["mus"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_mus_1"] if t in teachers]
            ),
            "armstrong": Classroom(
                id="armstrong",
                name="ARMSTRONG",
                subject_ids=["mus"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_mus_2"] if t in teachers]
            ),
            "euclide": Classroom(
                id="euclide",
                name="EUCLIDE",
                subject_ids=["mat"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_mat_1", "doc_mat_2", "doc_mat_3"] if t in teachers]
            ),
            "pitagora": Classroom(
                id="pitagora",
                name="PITAGORA",
                subject_ids=["mat"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_mat_4", "doc_mat_5"] if t in teachers]
            ),
            "eulero": Classroom(
                id="eulero",
                name="EULERO",
                subject_ids=["mat"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_mat_6", "doc_mat_7", "doc_mat_3"] if t in teachers]
            ),
            "chichibio": Classroom(
                id="chichibio",
                name="CHICHIBIO",
                subject_ids=["ita"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_1", "doc_let_2"] if t in teachers]
            ),
            "antigone": Classroom(
                id="antigone",
                name="ANTIGONE",
                subject_ids=["ita"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_3", "doc_let_4", "doc_let_5"] if t in teachers]
            ),
            "pinocchio": Classroom(
                id="pinocchio",
                name="PINOCCHIO",
                subject_ids=["ita"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_6", "doc_let_7"] if t in teachers]
            ),
            "didone": Classroom(
                id="didone",
                name="DIDONE",
                subject_ids=["ita"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_8", "doc_let_9"] if t in teachers]
            ),
            "queen": Classroom(
                id="queen",
                name="QUEEN",
                subject_ids=["ing"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_ing_1", "doc_ing_2"] if t in teachers]
            ),
            "strawberry": Classroom(
                id="strawberry",
                name="STRAWBERRY",
                subject_ids=["ing"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_ing_2", "doc_ing_3"] if t in teachers]
            ),
            "gagarin": Classroom(
                id="gagarin",
                name="GAGARIN",
                subject_ids=["geo", "sto", "tea", "app_custom"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_10", "doc_let_1", "doc_let_7"] if t in teachers]
            ),
            "marco_polo": Classroom(
                id="marco_polo",
                name="MARCO POLO",
                subject_ids=["geo", "sto"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_let_5", "doc_let_3", "doc_let_8"] if t in teachers]
            ),
            "verne": Classroom(
                id="verne",
                name="VERNE",
                subject_ids=["spa"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_spa_1"] if t in teachers]
            ),
            "moliere": Classroom(
                id="moliere",
                name="MOLIERE",
                subject_ids=["spa"],
                capacity=1,
                is_special_lab=False,
                priority=1,
                teacher_ids=[t for t in ["doc_spa_2"] if t in teachers]
            ),
            "monet": Classroom(
                id="monet",
                name="MONET",
                subject_ids=["art"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_art_1", "doc_art_2"] if t in teachers]
            ),
            "miro": Classroom(
                id="miro",
                name="MIRO'",
                subject_ids=["art"],
                capacity=1,
                is_special_lab=True,
                priority=1,
                teacher_ids=[t for t in ["doc_art_3", "doc_art_2"] if t in teachers]
            ),
            "r2_d2": Classroom(
                id="r2_d2",
                name="R2-D2",
                subject_ids=["tec"],
                capacity=1,
                is_special_lab=True,
                priority=2,
                teacher_ids=[]
            ),
            "auditorium": Classroom(
                id="auditorium",
                name="AUDITORIUM",
                subject_ids=["tea", "app_custom", "geo", "sto", "ita"],
                capacity=1,
                is_special_lab=True,
                priority=2,
                teacher_ids=[t for t in ["doc_let_4", "doc_let_10", "doc_let_7", "doc_let_1", "doc_let_8", "doc_let_6", "doc_let_11", "doc_let_3", "doc_let_2"] if t in teachers]
            ),
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

    # 6. Alunni DVA (23 Casi: max 2 per classe, 16 a 18h [6 gravi], 7 a 9h)
    students_dva = {}
    support_assignments = []
    enhancement_assignments = []
    
    if len(class_keys) >= 2:
        # Definizione del catalogo Casi DVA
        dva_specs_catalog = [
            # 6 Casi Gravi (18h ciascuno, rapporto 1:1)
            ("stud_dva_1", "Alunno Rossi M.", 0, 18, True, ["ita", "mat", "ing"], ["mot"], "Caso Grave (1:1) - Supporto continuo"),
            ("stud_dva_2", "Alunno Ferrari G.", 1, 18, True, ["ita", "mat", "sci"], ["rel"], "Caso Grave (1:1) - Supporto continuo"),
            ("stud_dva_3", "Alunno Romano L.", 2, 18, True, ["ita", "mat", "tec"], ["mot"], "Caso Grave (1:1) - Supporto continuo"),
            ("stud_dva_4", "Alunno Colombo S.", 3, 18, True, ["ita", "mat", "sto"], ["rel"], "Caso Grave (1:1) - Supporto continuo"),
            ("stud_dva_5", "Alunno Ricci A.", 4, 18, True, ["ita", "mat", "ing"], ["mot"], "Caso Grave (1:1) - Supporto continuo"),
            ("stud_dva_6", "Alunno Marino E.", 5, 18, True, ["ita", "mat", "sci"], ["mus"], "Caso Grave (1:1) - Supporto continuo"),

            # 10 Casi Medi da 18h
            ("stud_dva_7", "Alunno Bianchi F.", 0, 18, False, ["mat", "sci", "tec"], ["rel"], "Supporto logico-scientifico"),
            ("stud_dva_8", "Alunno Conti D.", 1, 18, False, ["ita", "sto", "geo"], ["mot"], "Supporto linguistico-espressivo"),
            ("stud_dva_9", "Alunno De Luca P.", 2, 18, False, ["mat", "tec", "ing"], ["art"], "Supporto materie tecniche"),
            ("stud_dva_10", "Alunno Costa V.", 6, 18, False, ["ita", "mat", "sci"], [], "Supporto generale"),
            ("stud_dva_11", "Alunno Giordano M.", 7, 18, False, ["ita", "sto", "ing"], ["mot"], "Supporto area umanistica"),
            ("stud_dva_12", "Alunno Mancini R.", 8, 18, False, ["mat", "sci", "tec"], ["rel"], "Supporto area scientifica"),
            ("stud_dva_13", "Alunno Rizzo K.", 9, 18, False, ["ita", "mat", "ing"], [], "Supporto discipline di base"),
            ("stud_dva_14", "Alunno Lombardi T.", 10, 18, False, ["ita", "sto", "geo"], ["mus"], "Supporto area linguistica"),
            ("stud_dva_15", "Alunno Moretti N.", 11, 18, False, ["mat", "sci", "tec"], ["art"], "Supporto tecnologico"),
            ("stud_dva_16", "Alunno Barbieri C.", 12, 18, False, ["ita", "mat", "sci"], ["mot"], "Supporto didattico"),

            # 7 Casi da 9h (Spezzoni / Autonomia parziale)
            ("stud_dva_17", "Alunno Santoro I.", 3, 9, False, ["mat", "sci"], ["mot", "mus"], "Spezzone 9h - Supporto matematica"),
            ("stud_dva_18", "Alunno Marini G.", 4, 9, False, ["ita", "ing"], ["rel", "art"], "Spezzone 9h - Supporto lingue"),
            ("stud_dva_19", "Alunno Rinaldi B.", 5, 9, False, ["mat", "tec"], ["mot", "rel"], "Spezzone 9h - Supporto scienze"),
            ("stud_dva_20", "Alunno Caruso H.", 6, 9, False, ["ita", "sto"], ["mus", "art"], "Spezzone 9h - Supporto lettere"),
            ("stud_dva_21", "Alunno Ferrara O.", 7, 9, False, ["mat", "sci"], ["mot", "rel"], "Spezzone 9h - Supporto matematica"),
            ("stud_dva_22", "Alunno Galli J.", 15, 9, False, ["ita", "ing"], ["art", "rel"], "Spezzone 9h - Supporto inglese"),
            ("stud_dva_23", "Alunno Martini Y.", 16, 9, False, ["mat", "sci"], ["mot", "mus"], "Spezzone 9h - Supporto logica")
        ]

        sos_last_names = [
            "Gentile", "Marini", "Serra", "Coppola", "Amato", "Fabbri", "Gatti", "Pellegrini",
            "Palumbo", "Sanna", "Grasso", "Monti", "Riva", "Donati", "Carbone", "D'Amico",
            "Castelli", "Ferraro", "Basile", "Vitale"
        ]

        if len(class_keys) >= 18:
            num_sos_teachers = 20
            dva_specs = dva_specs_catalog
        else:
            # Scala proporzionalmente: circa 1 docente di sostegno ogni 1-2 classi
            num_sos_teachers = min(len(sos_last_names), max(1, len(class_keys) // 2 + (1 if len(class_keys) % 2 != 0 else 0)))
            dva_specs = dva_specs_catalog[:max(2, num_sos_teachers * 2)]

        # Popola students_dva (usa s_name pulito senza duplicare la classe)
        for s_idx_num, (s_id, s_name, c_idx, s_hours, s_sev, s_pref, s_excl, s_notes) in enumerate(dva_specs):
            target_c = class_keys[s_idx_num % len(class_keys)]
            students_dva[s_id] = StudentDVA(
                id=s_id,
                name=s_name,
                class_id=target_c,
                weekly_hours=s_hours,
                is_severe_coverage=s_sev,
                preferred_subjects=s_pref,
                excluded_subjects=s_excl,
                preferred_hours=[0, 1, 2, 3],
                notes=s_notes
            )

        spec_by_id = {s[0]: s for s in dva_specs}
        dva_ids_list = list(students_dva.keys())

        # Creazione dei docenti di sostegno
        for t_i in range(num_sos_teachers):
            t_id = f"doc_sos_{t_i+1}"
            cognome = sos_last_names[t_i % len(sos_last_names)]
            free_d = [DAYS_OF_WEEK[t_i % 5]] if num_days == 6 else []
            
            p_areas = ["scientifica"] if t_i % 4 == 0 else (["umanistica"] if t_i % 4 == 1 else (["artistica"] if t_i % 4 == 2 else ["lingue"]))
            
            create_and_add_teacher(
                t_id, f"Prof. {cognome} (Sostegno 18h)", "ADMM - Sostegno", 18, 
                is_pt=False, 
                free_days=free_d,
                preferred_areas=p_areas
            )
            
            # Assegna 2 casi da 9h (oppure 1 caso da 18h)
            if len(dva_ids_list) >= 2:
                s1_id = dva_ids_list[(t_i * 2) % len(dva_ids_list)]
                s2_id = dva_ids_list[(t_i * 2 + 1) % len(dva_ids_list)]
                s1_obj = students_dva[s1_id]
                s2_obj = students_dva[s2_id]
                
                support_assignments.append(SupportAssignment(
                    id=f"sa_{t_id}_{s1_obj.class_id}_{s1_id}",
                    teacher_id=t_id,
                    student_id=s1_id,
                    class_id=s1_obj.class_id,
                    hours_per_week=9,
                    preferred_subject_ids=s1_obj.preferred_subjects
                ))
                support_assignments.append(SupportAssignment(
                    id=f"sa_{t_id}_{s2_obj.class_id}_{s2_id}",
                    teacher_id=t_id,
                    student_id=s2_id,
                    class_id=s2_obj.class_id,
                    hours_per_week=9,
                    preferred_subject_ids=s2_obj.preferred_subjects
                ))

        # Docente di Potenziamento
        create_and_add_teacher("doc_pot_1", "Prof.ssa Palumbo (Potenziamento Lettere)", "A-22 - Lettere (Potenziamento)", 18, is_pt=False)
        enhancement_assignments.append(EnhancementAssignment(
            id="pot_ita_1",
            teacher_id="doc_pot_1",
            subject_id="ita",
            hours_per_week=18,
            target_class_ids=list(class_keys),
            activity_type="compresenza"
        ))

    return TimetableProblem(
        config=config,
        teachers=teachers,
        classes=classes,
        subjects=subjects,
        rooms=rooms,
        assignments=assignments,
        students_dva=students_dva,
        support_assignments=support_assignments,
        enhancement_assignments=enhancement_assignments
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

def get_official_dada_rooms(teachers: Optional[Dict[str, Teacher]] = None) -> Dict[str, Classroom]:
    """Restituisce il dizionario delle 26 aule/laboratori ufficiali DADA con docenti assegnati."""
    t_map = teachers if teachers is not None else {}
    return {
        "leonardo": Classroom(
            id="leonardo",
            name="LEONARDO",
            subject_ids=["tec", "sci"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_tec_1", "doc_mat_1", "doc_mat_6"] if not t_map or t in t_map]
        ),
        "archimede": Classroom(
            id="archimede",
            name="ARCHIMEDE",
            subject_ids=["tec"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_tec_2"] if not t_map or t in t_map]
        ),
        "magellano": Classroom(
            id="magellano",
            name="MAGELLANO",
            subject_ids=["sto", "geo"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_2", "doc_let_9", "doc_let_4", "doc_let_6"] if not t_map or t in t_map]
        ),
        "bebe_vio": Classroom(
            id="bebe_vio",
            name="BEBE VIO",
            subject_ids=["mot"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_mot_1", "doc_mot_2", "doc_mot_3"] if not t_map or t in t_map]
        ),
        "palestra_murato": Classroom(
            id="palestra_murato",
            name="PALESTRA MURATO",
            subject_ids=["mot"],
            capacity=1,
            is_special_lab=True,
            priority=2,
            teacher_ids=[t for t in ["doc_mot_4", "doc_mot_1"] if not t_map or t in t_map]
        ),
        "galileo": Classroom(
            id="galileo",
            name="GALILEO",
            subject_ids=["sci"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_mat_7", "doc_mat_5", "doc_mat_2", "doc_mat_4", "doc_mat_3", "doc_mat_6"] if not t_map or t in t_map]
        ),
        "maddalena_malal": Classroom(
            id="maddalena_malal",
            name="MADDALENA-MALAL",
            subject_ids=["rel"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_rel_1"] if not t_map or t in t_map]
        ),
        "bach": Classroom(
            id="bach",
            name="BACH",
            subject_ids=["mus"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_mus_1"] if not t_map or t in t_map]
        ),
        "armstrong": Classroom(
            id="armstrong",
            name="ARMSTRONG",
            subject_ids=["mus"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_mus_2"] if not t_map or t in t_map]
        ),
        "euclide": Classroom(
            id="euclide",
            name="EUCLIDE",
            subject_ids=["mat"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_mat_1", "doc_mat_2", "doc_mat_3"] if not t_map or t in t_map]
        ),
        "pitagora": Classroom(
            id="pitagora",
            name="PITAGORA",
            subject_ids=["mat"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_mat_4", "doc_mat_5"] if not t_map or t in t_map]
        ),
        "eulero": Classroom(
            id="eulero",
            name="EULERO",
            subject_ids=["mat"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_mat_6", "doc_mat_7", "doc_mat_3"] if not t_map or t in t_map]
        ),
        "chichibio": Classroom(
            id="chichibio",
            name="CHICHIBIO",
            subject_ids=["ita"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_1", "doc_let_2"] if not t_map or t in t_map]
        ),
        "antigone": Classroom(
            id="antigone",
            name="ANTIGONE",
            subject_ids=["ita"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_3", "doc_let_4", "doc_let_5"] if not t_map or t in t_map]
        ),
        "pinocchio": Classroom(
            id="pinocchio",
            name="PINOCCHIO",
            subject_ids=["ita"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_6", "doc_let_7"] if not t_map or t in t_map]
        ),
        "didone": Classroom(
            id="didone",
            name="DIDONE",
            subject_ids=["ita"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_8", "doc_let_9"] if not t_map or t in t_map]
        ),
        "queen": Classroom(
            id="queen",
            name="QUEEN",
            subject_ids=["ing"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_ing_1", "doc_ing_2"] if not t_map or t in t_map]
        ),
        "strawberry": Classroom(
            id="strawberry",
            name="STRAWBERRY",
            subject_ids=["ing"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_ing_2", "doc_ing_3"] if not t_map or t in t_map]
        ),
        "gagarin": Classroom(
            id="gagarin",
            name="GAGARIN",
            subject_ids=["geo", "sto", "tea", "app_custom"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_10", "doc_let_1", "doc_let_7"] if not t_map or t in t_map]
        ),
        "marco_polo": Classroom(
            id="marco_polo",
            name="MARCO POLO",
            subject_ids=["geo", "sto"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_let_5", "doc_let_3", "doc_let_8"] if not t_map or t in t_map]
        ),
        "verne": Classroom(
            id="verne",
            name="VERNE",
            subject_ids=["spa"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_spa_1"] if not t_map or t in t_map]
        ),
        "moliere": Classroom(
            id="moliere",
            name="MOLIERE",
            subject_ids=["spa"],
            capacity=1,
            is_special_lab=False,
            priority=1,
            teacher_ids=[t for t in ["doc_spa_2"] if not t_map or t in t_map]
        ),
        "monet": Classroom(
            id="monet",
            name="MONET",
            subject_ids=["art"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_art_1", "doc_art_2"] if not t_map or t in t_map]
        ),
        "miro": Classroom(
            id="miro",
            name="MIRO'",
            subject_ids=["art"],
            capacity=1,
            is_special_lab=True,
            priority=1,
            teacher_ids=[t for t in ["doc_art_3", "doc_art_2"] if not t_map or t in t_map]
        ),
        "r2_d2": Classroom(
            id="r2_d2",
            name="R2-D2",
            subject_ids=["tec"],
            capacity=1,
            is_special_lab=True,
            priority=2,
            teacher_ids=[]
        ),
        "auditorium": Classroom(
            id="auditorium",
            name="AUDITORIUM",
            subject_ids=["tea", "app_custom", "geo", "sto", "ita"],
            capacity=1,
            is_special_lab=True,
            priority=2,
            teacher_ids=[t for t in ["doc_let_4", "doc_let_10", "doc_let_7", "doc_let_1", "doc_let_8", "doc_let_6", "doc_let_11", "doc_let_3", "doc_let_2"] if not t_map or t in t_map]
        ),
    }
