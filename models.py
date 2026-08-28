"""
Modelli di dati per l'applicazione di generazione dell'orario scolastico.
Supporta scuole secondarie di I e II grado con gestione contrattuale precisa del Part-Time
(Monte ore settimanale + articolazione su massimo N giorni).
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

DAYS_OF_WEEK = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato"]

DISCIPLINARY_AREAS = {
    "scientifica": {
        "label": "📐 Area Scientifica",
        "subjects": ["mat", "sci", "tec"],
        "desc": "Matematica, Scienze, Tecnologia"
    },
    "umanistica": {
        "label": "📖 Area Umanistica / Lettere",
        "subjects": ["ita", "sto", "geo"],
        "desc": "Italiano, Storia, Geografia"
    },
    "artistica": {
        "label": "🎨 Area Artistico-Espressiva",
        "subjects": ["art", "mus", "mot", "rel"],
        "desc": "Arte, Musica, Scienze Motorie, Religione"
    },
    "lingue": {
        "label": "🌍 Area Lingue Straniere",
        "subjects": ["ing", "spa"],
        "desc": "Inglese, Seconda Lingua (Spagnolo/Francese)"
    }
}

@dataclass
class Classroom:
    id: str
    name: str                        # es: "Aula Lettere 1", "Lab. Fisica", "Palestra"
    subject_ids: List[str] = field(default_factory=list) # Materie che possono utilizzare quest'aula
    teacher_ids: List[str] = field(default_factory=list) # Docenti specifici assegnati a quest'aula (es. aula personale / dipartimento)
    capacity: int = 1                # Quante classi possono usarla contemporaneamente
    is_special_lab: bool = False     # True se laboratorio/palestra, False se aula ordinaria/DADA
    priority: int = 1                # Priorità di utilizzo: 1 = Massima / Principale, 2 = Secondaria, 3 = Riserva

@dataclass
class Teacher:
    id: str
    name: str
    cdc: str = ""                          # Classe di Concorso (es. A-22 Lettere, A-28 Mat/Sci, A-24 Lingue, A-60 Tec, A-30 Mus, A-01 Arte, A-48 Mot, Religione, ADMM Sostegno)
    is_part_time: bool = False             # True se docente part-time o spezzone
    contract_hours: Optional[int] = None   # Monte ore contrattuale dichiarato (es. 6, 9, 12, 14 ore)
    max_working_days: Optional[int] = None # Articolazione: numero MASSIMO di giorni di presenza a scuola (es. max 2 o 3 gg)
    
    free_day_1: Optional[str] = None       # Prima scelta giorno libero preferito (legacy/compatibilità)
    free_day_2: Optional[str] = None       # Seconda scelta giorno libero preferito (legacy/compatibilità)
    free_days: List[str] = field(default_factory=list) # Lista completa giorni liberi preferiti (fino a N giorni per part-time)
    
    # Desiderata e Affinità Disciplinari Sostegno
    preferred_areas: List[str] = field(default_factory=list) # Aree disciplinari preferite per i docenti di sostegno (es. ["scientifica", "umanistica"])
    
    # Vincoli Rigidi (Inderogabili)
    unavailable_slots: List[List[int]] = field(default_factory=list) # Slot [day_idx, hour_idx] vietati al 100% (Escludi)
    required_slots: List[List[int]] = field(default_factory=list)    # Slot [day_idx, hour_idx] di presenza tassativa (Includi / DEVE fare lezione)
    
    # Desiderata Flessibili (Soft Constraints ottimizzabili)
    prefer_late_entry: bool = False        # Desiderata: preferisce non fare la 1ª ora in generale
    prefer_early_exit: bool = False        # Desiderata: preferisce non fare l'ultima ora in generale
    late_entry_days: List[str] = field(default_factory=list) # Giorni specifici in cui non fare la 1ª ora (es. ["Lunedì", "Giovedì"])
    early_exit_days: List[str] = field(default_factory=list) # Giorni specifici in cui non fare l'ultima ora (es. ["Mercoledì", "Venerdì"])
    soft_avoid_slots: List[List[int]] = field(default_factory=list)  # Slot [day_idx, hour_idx] sconsigliati (es. no 1a ora merc)
    
    # Parametri Carico Orario
    min_daily_hours: int = 2               # Minimo numero di ore in un giorno se presente (default 2h)
    max_daily_hours: int = 5               # Massimo numero di ore in un giorno (default 5h)
    max_consecutive_hours: int = 4         # Massimo ore consecutive di lezione (default 4h)
    max_gap_hours: int = 2                 # Massimo ore buche settimanali tollerate
    prefer_compact_schedule: bool = True   # Preferenza ore compatte (meno buchi possibili)

@dataclass
class SchoolClass:
    id: str
    name: str          # es: 1A, 2B, 1F Musicale, 2E Prolungato
    grade: int = 1     # Anno di corso (1..3)
    section: str = "A" # Sezione
    curriculum_type: str = "ordinario" # "ordinario" (30h), "musicale" (32h), "prolungato" (36h)
    weekly_hours_target: int = 30      # 30, 32 o 36 ore settimanali
    afternoon_days: List[str] = field(default_factory=list) # Giorni di rientro pomeridiano per questa specifica classe (es. ["Lunedì", "Mercoledì"])
    lunch_break_duration: int = 60     # Durata pausa mensa in minuti: 30, 60, 90 minuti

@dataclass
class Subject:
    id: str
    name: str          # es: Italiano, Matematica, Scienze Motorie, Musica d'Insieme / Orchestra, Teoria e Solfeggio
    color: str = "#3498db" # Colore per visualizzazione tabellare
    cdc: str = ""          # Classe di Concorso ministeriale (es. A-22, A-28, A-24, A-60, A-30, A-56 Strumento, A-01, A-48, Religione)
    special_room_id: Optional[str] = None # Eventuale aula fissa o laboratorio / auditorium
    default_double_hours: bool = False    # Se True, accoppia forzatamente in blocchi da 2h consecutive
    is_musical_discipline: bool = False   # True per Orchestra, Teoria/Solfeggio, Strumento
    is_extended_time_discipline: bool = False # True per laboratori/compresenze specifiche del tempo prolungato

@dataclass
class TeachingAssignment:
    id: str
    teacher_id: str
    class_id: str
    subject_id: str
    hours_per_week: int
    allow_double_hours: bool = False      # Permette blocchi da 2 ore
    force_double_hours: bool = False      # Richiede esplicitamente blocchi da 2 ore
    force_triple_hours: bool = False      # Richiede esplicitamente 1 blocco da 3 ore (es. tema di lettere)
    max_daily_hours: int = 2              # Max ore al giorno per questa materia in questa classe
    preferred_room_id: Optional[str] = None # Aula specifica opzionale
    co_teacher_ids: List[str] = field(default_factory=list) # Fino a 4 docenti in compresenza (es. i 4 docenti di strumento per Orchestra/Solfeggio o compresenze prolungato)
    pinned_slots: List[List[int]] = field(default_factory=list) # Slot [day_idx, hour_idx] in cui QUESTA lezione è bloccata/fissata
    preferred_time_of_day: str = "any"    # "any", "morning_only" (antimeridiana), "afternoon_only" (postmeridiana/rientro)

@dataclass
class StudentDVA:
    id: str                                    # Identificativo univoco (es. "stud_1")
    name: str                                  # Nome o codice alunno (es. "Alunno A.B.")
    class_id: str                              # Classe di appartenenza (es. "1A")
    weekly_hours: int = 18                     # Ore settimanali di sostegno assegnate da PEI
    is_severe_coverage: bool = False           # True = Caso Grave (Non può stare solo, serve sempre copertura continua 1:1)
    preferred_subjects: List[str] = field(default_factory=list) # Materie prioritarie da coprire (es. ["ita", "mat", "ing"])
    excluded_subjects: List[str] = field(default_factory=list)  # Materie a bassa priorità / non coperte (es. ["mot", "rel"])
    preferred_hours: List[int] = field(default_factory=list)    # Slot orari preferiti della giornata (es. prime 4 ore [0, 1, 2, 3])
    notes: str = ""                            # Eventuali note pedagogiche

@dataclass
class SupportAssignment:
    id: str                                    # Identificativo (es. "sa_1")
    teacher_id: str                            # Docente di sostegno
    student_id: Optional[str] = None           # Alunno DVA associato (opzionale se assegnato a classe)
    class_id: str = ""                         # Classe su cui opera
    hours_per_week: int = 18                   # Ore settimanali assegnate
    preferred_subject_ids: List[str] = field(default_factory=list) # Materie di affinità/preferite dal docente

@dataclass
class EnhancementAssignment:
    id: str                                    # Identificativo (es. "pot_1")
    teacher_id: str                            # Docente di potenziamento
    subject_id: str                            # Disciplina / CdC (es. "ita", "mat")
    hours_per_week: int = 18                   # Ore settimanali di potenziamento
    target_class_ids: List[str] = field(default_factory=list) # Classi su cui intervenire per compresenze/recupero
    activity_type: str = "compresenza"         # "compresenza", "recupero", "laboratorio", "mensa"

@dataclass
class OptimizationCriteria:
    max_gap_limit: int = 4              # Tetto massimo ore buche per singolo docente (default 4h)
    strict_gap_limit: bool = True       # Vincolo rigido (tassativo <= max_gap_limit)
    enable_gap_fairness: bool = True    # Distribuzione omogenea ed equa delle buche tra tutti i docenti
    weight_gap_fairness: int = 180      # Peso minimizzazione picco ore buche (Min-Max fairness)
    weight_gap_hours: int = 80          # Peso minimizzazione totale ore buche
    weight_free_day_1: int = 200        # Peso soddisfazione giorno libero 1ª scelta
    weight_free_day_2: int = 120        # Peso soddisfazione giorno libero 2ª scelta
    weight_late_entry: int = 80         # Peso ingressi posticipati (No 1ª ora)
    weight_early_exit: int = 80         # Peso uscite anticipate (No ultima ora)
    weight_soft_slots: int = 50         # Peso slot sconsigliati
    weight_consecutive_blocks: int = 70 # Peso blocchi 2h consecutivi accoppiati

@dataclass
class ParallelGroup:
    id: str
    name: str                                  # es: "Scienze Motorie Prime (1A + 1D)", "Italiano Parallelo Prime"
    subject_id: str                            # es: "mot", "ita", "spa"
    class_ids: List[str] = field(default_factory=list) # Classi sincronizzate nello stesso orario
    parallel_hours: int = 2                    # Quante ore settimanali sincronizzate (default 2h)
    force_consecutive_block: bool = True       # Se le ore parallele devono essere in un unico blocco da 2h
    room_id: Optional[str] = None              # Eventuale aula/palestra comune condivisa (se None: aule separate)
    is_same_teacher_merged: bool = False       # True se le classi sono accorpate con un UNICO docente (compresenza/classe unica)
    is_active: bool = True                     # Abilitato / Disabilitato

@dataclass
class SchoolConfig:
    num_days: int = 5                     # 5 (settimana corta) o 6 (settimana lunga)
    daily_hours: List[int] = field(default_factory=lambda: [6, 6, 6, 6, 6]) # Ore per ciascun giorno (0-indexed)
    school_name: str = "Scuola Secondaria di I Grado"
    school_type: str = "Secondaria I Grado (Scuola Media)"
    is_dada: bool = False                 # Flag Modello DADA (Aule per Disciplina)
    dada_prefer_double_hours: bool = True # Politica DADA: accorpa a blocchi da 2h quando possibile per ridurre spostamenti
    dada_block_strategy: str = "maximize_blocks" # "maximize_blocks" (accorpa sempre a 2h se >=2h) o "custom"
    dada_strict_even_pairs: bool = False  # Se True in DADA, vincola i blocchi da 2h solo a slot fissi 1-2, 3-4, 5-6 (cambio aula solo a intervallo)
    second_language: str = "Spagnolo"     # "Spagnolo", "Francese", "Tedesco", ecc.
    approfondimento_type: str = "subject" # "subject" (potenziamento) oppure "custom_activity" (es. Teatro, Coding)
    approfondimento_subject: str = "ita"  # Materia potenziata (ita, mat, sci, ing, tec, spa)
    approfondimento_custom_name: str = "Laboratorio di Teatro" # Nome attività dedicata
    approfondimento_cdc: str = "A-22"     # Classe di concorso a cui è attribuita l'attività (es. A-22 Lettere per Teatro)
    approfondimento_deduct_from: str = "ita" # Disciplina da cui sottrarre 1h se la CdC fa più materie (es. 'ita' per A-22 o 'mat' per A-28)
    approfondimento_custom_room: Optional[str] = "aula_teatro" # Aula / Spazio dedicato (es. Aula Magna, Teatro)
    subject_block_preferences: Dict[str, bool] = field(default_factory=dict) # Mappa per materia: {subject_id: force_double_hours}
    allow_triple_hours_italian: bool = False # Se True, consente fino a 3h di Italiano nello stesso giorno (es. per Tema)
    force_triple_hours_italian: bool = False # Se True a livello di istituto, impone 1 blocco da 3h consecutive di Italiano per tutte le classi
    
    # Parametri Musicale & Tempo Prolungato
    has_musical_curriculum: bool = False  # Se la scuola ha sezioni a indirizzo musicale (32h)
    musical_instruments: List[str] = field(default_factory=lambda: ["Flauto", "Violino", "Chitarra", "Clarinetto"]) # 4 strumenti
    musical_orchestra_co_teachers: int = 4 # Quanti docenti in compresenza per Orchestra / Teoria (fino a 4)
    default_lunch_break_duration: int = 60 # 30, 60 o 90 minuti
    
    parallel_groups: List[ParallelGroup] = field(default_factory=list) # Gruppi di Classi Aperte & Parallelismi Didattici
    support_priority_subjects_double_coverage: List[str] = field(default_factory=lambda: ["ita", "mat", "sci", "ing", "tec"]) # Materie prioritarie per compresenza/doppia copertura sostegno
    optimization_criteria: OptimizationCriteria = field(default_factory=OptimizationCriteria) # Criteri e pesi di ottimizzazione

    @property
    def total_weekly_slots(self) -> int:
        return sum(self.daily_hours[:self.num_days])

    @property
    def active_days(self) -> List[str]:
        return DAYS_OF_WEEK[:self.num_days]

@dataclass
class TimetableProblem:
    config: SchoolConfig
    teachers: Dict[str, Teacher] = field(default_factory=dict)
    classes: Dict[str, SchoolClass] = field(default_factory=dict)
    subjects: Dict[str, Subject] = field(default_factory=dict)
    rooms: Dict[str, Classroom] = field(default_factory=dict)
    assignments: List[TeachingAssignment] = field(default_factory=list)
    students_dva: Dict[str, StudentDVA] = field(default_factory=dict)
    support_assignments: List[SupportAssignment] = field(default_factory=list)
    enhancement_assignments: List[EnhancementAssignment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TimetableProblem':
        cfg_data = data.get("config", {})
        opt_data = cfg_data.get("optimization_criteria", {})
        if opt_data and isinstance(opt_data, dict):
            opt_criteria = OptimizationCriteria(**opt_data)
        else:
            opt_criteria = OptimizationCriteria()

        p_groups_data = cfg_data.get("parallel_groups", [])
        p_groups = []
        for pg in p_groups_data:
            if isinstance(pg, dict):
                p_groups.append(ParallelGroup(**pg))
            elif isinstance(pg, ParallelGroup):
                p_groups.append(pg)

        config = SchoolConfig(
            num_days=cfg_data.get("num_days", 5),
            daily_hours=cfg_data.get("daily_hours", [6, 6, 6, 6, 6]),
            school_name=cfg_data.get("school_name", "Scuola Secondaria di I Grado"),
            school_type=cfg_data.get("school_type", "Secondaria I Grado (Scuola Media)"),
            is_dada=cfg_data.get("is_dada", False),
            dada_prefer_double_hours=cfg_data.get("dada_prefer_double_hours", True),
            dada_block_strategy=cfg_data.get("dada_block_strategy", "maximize_blocks"),
            dada_strict_even_pairs=cfg_data.get("dada_strict_even_pairs", False),
            second_language=cfg_data.get("second_language", "Spagnolo"),
            approfondimento_type=cfg_data.get("approfondimento_type", "subject"),
            approfondimento_subject=cfg_data.get("approfondimento_subject", "ita"),
            approfondimento_custom_name=cfg_data.get("approfondimento_custom_name", "Laboratorio di Teatro"),
            approfondimento_cdc=cfg_data.get("approfondimento_cdc", "A-22"),
            approfondimento_deduct_from=cfg_data.get("approfondimento_deduct_from", "ita"),
            approfondimento_custom_room=cfg_data.get("approfondimento_custom_room", None),
            subject_block_preferences=cfg_data.get("subject_block_preferences", {}),
            allow_triple_hours_italian=cfg_data.get("allow_triple_hours_italian", False),
            force_triple_hours_italian=cfg_data.get("force_triple_hours_italian", False),
            parallel_groups=p_groups,
            support_priority_subjects_double_coverage=cfg_data.get("support_priority_subjects_double_coverage", ["ita", "mat", "sci", "ing", "tec"]),
            optimization_criteria=opt_criteria
        )
        
        teachers = {}
        for k, v in data.get("teachers", {}).items():
            f_days = v.get("free_days", [])
            if not f_days:
                if v.get("free_day_1"): f_days.append(v.get("free_day_1"))
                if v.get("free_day_2"): f_days.append(v.get("free_day_2"))
            teachers[k] = Teacher(
                id=v.get("id", k),
                name=v.get("name", k),
                cdc=v.get("cdc", ""),
                is_part_time=v.get("is_part_time", False),
                contract_hours=v.get("contract_hours"),
                max_working_days=v.get("max_working_days"),
                free_day_1=v.get("free_day_1") or (f_days[0] if f_days else None),
                free_day_2=v.get("free_day_2") or (f_days[1] if len(f_days) > 1 else None),
                free_days=f_days,
                unavailable_slots=v.get("unavailable_slots", []),
                required_slots=v.get("required_slots", []),
                prefer_late_entry=v.get("prefer_late_entry", False),
                prefer_early_exit=v.get("prefer_early_exit", False),
                late_entry_days=v.get("late_entry_days", []),
                early_exit_days=v.get("early_exit_days", []),
                soft_avoid_slots=v.get("soft_avoid_slots", []),
                max_daily_hours=v.get("max_daily_hours", 5),
                max_consecutive_hours=v.get("max_consecutive_hours", 4),
                max_gap_hours=v.get("max_gap_hours", 2),
                prefer_compact_schedule=v.get("prefer_compact_schedule", True)
            )
            
        classes = {k: SchoolClass(**v) for k, v in data.get("classes", {}).items()}
        subjects = {}
        for k, v in data.get("subjects", {}).items():
            subjects[k] = Subject(
                id=v.get("id", k),
                name=v.get("name", k),
                color=v.get("color", "#3498db"),
                cdc=v.get("cdc", ""),
                special_room_id=v.get("special_room_id")
            )
        rooms = {}
        for k, v in data.get("rooms", {}).items():
            rooms[k] = Classroom(
                id=v.get("id", k),
                name=v.get("name", k),
                subject_ids=v.get("subject_ids", []),
                teacher_ids=v.get("teacher_ids", []),
                capacity=v.get("capacity", 1),
                is_special_lab=v.get("is_special_lab", False),
                priority=v.get("priority", 1)
            )
            
        assignments = []
        for a in data.get("assignments", []):
            assignments.append(TeachingAssignment(
                id=a.get("id", ""),
                teacher_id=a.get("teacher_id", ""),
                class_id=a.get("class_id", ""),
                subject_id=a.get("subject_id", ""),
                hours_per_week=a.get("hours_per_week", 2),
                allow_double_hours=a.get("allow_double_hours", False),
                force_double_hours=a.get("force_double_hours", False),
                force_triple_hours=a.get("force_triple_hours", False),
                max_daily_hours=a.get("max_daily_hours", 2),
                preferred_room_id=a.get("preferred_room_id"),
                co_teacher_ids=a.get("co_teacher_ids", []),
                pinned_slots=a.get("pinned_slots", [])
            ))

        students_dva = {}
        for k, v in data.get("students_dva", {}).items():
            if isinstance(v, dict):
                students_dva[k] = StudentDVA(**v)
            elif isinstance(v, StudentDVA):
                students_dva[k] = v

        support_assignments = []
        for sa in data.get("support_assignments", []):
            if isinstance(sa, dict):
                support_assignments.append(SupportAssignment(**sa))
            elif isinstance(sa, SupportAssignment):
                support_assignments.append(sa)

        enhancement_assignments = []
        for ea in data.get("enhancement_assignments", []):
            if isinstance(ea, dict):
                enhancement_assignments.append(EnhancementAssignment(**ea))
            elif isinstance(ea, EnhancementAssignment):
                enhancement_assignments.append(ea)

        return cls(
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
