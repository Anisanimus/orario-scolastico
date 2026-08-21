"""
Modulo per l'importazione ed esportazione di template CSV ed Excel (.xlsx).
Permette agli utenti di scaricare un template vuoto o di esempio, compilarlo con Excel o Calc,
e ricaricarlo per popolare automaticamente docenti, desiderata, classi, materie, cattedre e vincoli didattici.
"""
import io
import csv
import re
import pandas as pd
from typing import Tuple, List, Dict, Optional, Any
from models import (
    SchoolConfig, Teacher, SchoolClass, Subject, Classroom, 
    TeachingAssignment, TimetableProblem, DAYS_OF_WEEK
)

# Colonne ordinate logicamente: prima i dati della Cattedra, poi i Desiderata del Docente
CSV_HEADERS = [
    "Docente",
    "CdC",
    "Classe",
    "Materia",
    "Ore_Settimanali",
    "Ore_Doppie",
    "Max_Ore_Giorno_Materia",
    "Part_Time",
    "Ore_Contratto",
    "Max_Giorni_Presenza",
    "Giorni_Liberi",
    "Entra_Tardi",
    "Esce_Presto",
    "Max_Ore_Giorno_Docente",
    "Max_Ore_Buche",
    "Slot_Sconsigliati",
    "Slot_Indisponibili"
]

# Mappatura colori predefiniti per le materie
DEFAULT_SUBJECT_COLORS = {
    "ita": "#e74c3c", "italiano": "#e74c3c", "lettere": "#e74c3c",
    "sto": "#e67e22", "storia": "#e67e22",
    "geo": "#d35400", "geografia": "#d35400",
    "mat": "#2980b9", "matematica": "#2980b9",
    "sci": "#27ae60", "scienze": "#27ae60",
    "ing": "#8e44ad", "inglese": "#8e44ad",
    "spa": "#9b59b6", "spagnolo": "#9b59b6", "seconda lingua": "#9b59b6", "francese": "#9b59b6", "tedesco": "#9b59b6",
    "tec": "#16a085", "tecnologia": "#16a085", "coding": "#16a085", "informatica": "#16a085",
    "mus": "#f39c12", "musica": "#f39c12", "strumento": "#f39c12",
    "art": "#e84393", "arte": "#e84393", "arte e immagine": "#e84393",
    "mot": "#00b894", "scienze motorie": "#00b894", "motoria": "#00b894", "ed. fisica": "#00b894",
    "rel": "#7f8c8d", "religione": "#7f8c8d", "materia alternativa": "#7f8c8d",
    "teatro": "#fd79a8", "laboratorio teatro": "#fd79a8", "laboratorio di teatro": "#fd79a8"
}

def _build_rows_data(sample_problem: Optional[TimetableProblem] = None) -> List[List[Any]]:
    """Costruisce le righe dati ordinate logicamente per CSV ed Excel."""
    rows = []
    if sample_problem and sample_problem.assignments:
        # Ordina per docente e classe per massima leggibilità
        sorted_assigns = sorted(
            sample_problem.assignments, 
            key=lambda a: (
                sample_problem.teachers.get(a.teacher_id).name if a.teacher_id in sample_problem.teachers else "",
                sample_problem.classes.get(a.class_id).name if a.class_id in sample_problem.classes else ""
            )
        )
        for a in sorted_assigns:
            t = sample_problem.teachers.get(a.teacher_id)
            c = sample_problem.classes.get(a.class_id)
            s = sample_problem.subjects.get(a.subject_id)
            
            t_name = t.name if t else a.teacher_id
            t_cdc = getattr(t, "cdc", "") if t else (getattr(s, "cdc", "") if s else "")
            c_name = c.name if c else a.class_id
            s_name = s.name if s else a.subject_id
            a_hours = a.hours_per_week
            a_double = "Si" if a.force_double_hours else "No"
            a_max_d = a.max_daily_hours or 2
            
            t_pt = "Si" if (t and getattr(t, "is_part_time", False)) else "No"
            t_ch = getattr(t, "contract_hours", 18) if t else 18
            t_mwd = getattr(t, "max_working_days", 5) if t else 5
            
            f_list = getattr(t, "free_days", []) if t else []
            if not f_list and t:
                if getattr(t, "free_day_1", None): f_list.append(t.free_day_1)
                if getattr(t, "free_day_2", None): f_list.append(t.free_day_2)
            giorni_liberi_str = ", ".join(f_list) if f_list else ""
            
            t_late = "Si" if (t and getattr(t, "prefer_late_entry", False)) else "No"
            t_early = "Si" if (t and getattr(t, "prefer_early_exit", False)) else "No"
            t_mdh = getattr(t, "max_daily_hours", 5) if t else 5
            t_mgh = getattr(t, "max_gap_hours", 2) if t else 2
            
            soft_str = ""
            if t and getattr(t, "soft_avoid_slots", []):
                slot_strs = []
                for d_i, h_i in t.soft_avoid_slots:
                    if d_i < len(DAYS_OF_WEEK):
                        slot_strs.append(f"{DAYS_OF_WEEK[d_i]} {h_i+1}")
                soft_str = ", ".join(slot_strs)
                
            unavail_str = ""
            if t and getattr(t, "unavailable_slots", []):
                slot_strs = []
                for d_i, h_i in t.unavailable_slots:
                    if d_i < len(DAYS_OF_WEEK):
                        slot_strs.append(f"{DAYS_OF_WEEK[d_i]} {h_i+1}")
                unavail_str = ", ".join(slot_strs)

            rows.append([
                t_name,
                t_cdc,
                c_name,
                s_name,
                a_hours,
                a_double,
                a_max_d,
                t_pt,
                t_ch or 18,
                t_mwd or 5,
                giorni_liberi_str,
                t_late,
                t_early,
                t_mdh,
                t_mgh,
                soft_str,
                unavail_str
            ])
    else:
        # Righe di esempio chiare ed esplicative per il template vuoto
        rows = [
            [
                "Prof.ssa Bianchi", "A-22", "1ª A", "Italiano", 6, "Si", 2,
                "No", 18, 5, "", "No", "Si", 5, 2, "", ""
            ],
            [
                "Prof.ssa Bianchi", "A-22", "1ª A", "Storia", 2, "No", 2,
                "No", 18, 5, "", "No", "Si", 5, 2, "", ""
            ],
            [
                "Prof. Verdi", "A-28", "1ª A", "Matematica", 4, "Si", 2,
                "No", 18, 5, "", "Si", "No", 5, 1, "", ""
            ],
            [
                "Prof. Verdi", "A-28", "1ª A", "Scienze", 2, "No", 2,
                "No", 18, 5, "", "Si", "No", 5, 1, "", ""
            ],
            [
                "Prof.ssa Colombo", "A-24", "1ª A", "Seconda Lingua (Spagnolo)", 2, "No", 2,
                "Si", 12, 3, "Lunedì, Mercoledì", "No", "No", 4, 1, "Mercoledì 1", "Lunedì 6"
            ]
        ]
    return rows

def generate_csv_template(sample_problem: Optional[TimetableProblem] = None) -> str:
    """
    Genera il contenuto CSV (con separatore punto e virgola ';' ideale per Excel italiano).
    """
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_HEADERS)
    for r in _build_rows_data(sample_problem):
        writer.writerow(r)
    return output.getvalue()

def generate_excel_template(sample_problem: Optional[TimetableProblem] = None) -> bytes:
    """
    Genera un file Excel (.xlsx) formattato con intestazioni in evidenza e larghezza colonne automatica.
    """
    rows = _build_rows_data(sample_problem)
    df = pd.DataFrame(rows, columns=CSV_HEADERS)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Cattedre_e_Docenti', index=False)
        
        # Formattazione grafica del foglio Excel
        ws = writer.sheets['Cattedre_e_Docenti']
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )
        
        for col_num, col_name in enumerate(CSV_HEADERS, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align
            
            # Adatta la larghezza della colonna
            max_len = max([len(str(r[col_num-1])) for r in rows] + [len(col_name)]) + 4
            col_letter = cell.column_letter
            ws.column_dimensions[col_letter].width = max(max_len, 14)
            
        # Applica bordi a tutte le celle
        for row in ws.iter_rows(min_row=2, max_row=len(rows)+1, min_col=1, max_col=len(CSV_HEADERS)):
            for cell in row:
                cell.border = thin_border
                if cell.column in [5, 6, 7, 8, 9, 10, 12, 13, 14, 15]:
                    cell.alignment = center_align
                else:
                    cell.alignment = left_align
                    
    return output.getvalue()


def _parse_bool(val: Any) -> bool:
    if not val or pd.isna(val):
        return False
    v = str(val).strip().lower()
    return v in ["si", "sì", "yes", "true", "1", "s", "y"]

def _parse_int(val: Any, default: int = 0) -> int:
    if val is None or pd.isna(val) or val == "":
        return default
    try:
        return int(float(str(val).strip().replace(",", ".")))
    except:
        return default

def _clean_id(name: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_]', '_', name.strip().lower()).strip('_')

def _parse_slots_str(text: Any) -> List[List[int]]:
    """Converte stringhe come 'Mercoledì 1, Venerdì 5' o 'Lun 2; Ven 6' in [[day, hour], ...]"""
    if not text or pd.isna(text) or not str(text).strip():
        return []
    
    day_map = {
        "lun": 0, "luned": 0, "mon": 0,
        "mar": 1, "marted": 1, "tue": 1,
        "mer": 2, "mercol": 2, "wed": 2,
        "gio": 3, "gioved": 3, "thu": 3,
        "ven": 4, "venerd": 4, "fri": 4,
        "sab": 5, "sabat": 5, "sat": 5,
    }
    
    results = []
    parts = re.split(r'[,;/|]+', str(text))
    for part in parts:
        p = part.strip().lower()
        if not p:
            continue
        
        found_day = None
        for k, d_idx in day_map.items():
            if k in p:
                found_day = d_idx
                break
                
        num_match = re.search(r'(\d+)', p)
        if found_day is not None and num_match:
            h_num = int(num_match.group(1)) - 1 # 0-indexed
            if 0 <= h_num <= 8:
                results.append([found_day, h_num])
                
    return results

def _parse_free_days(text: Any) -> List[str]:
    """Estrae i giorni liberi da testo come 'Lunedì, Mercoledì' o 'Martedi'"""
    if not text or pd.isna(text) or not str(text).strip():
        return []
    
    day_patterns = {
        "Lunedì": ["lun"],
        "Martedì": ["mar"],
        "Mercoledì": ["mer"],
        "Giovedì": ["gio"],
        "Venerdì": ["ven"],
        "Sabato": ["sab"]
    }
    
    found = []
    parts = re.split(r'[,;/|]+', str(text).strip().lower())
    for part in parts:
        p = part.strip()
        for formal_name, subpatterns in day_patterns.items():
            if any(sub in p for sub in subpatterns):
                if formal_name not in found:
                    found.append(formal_name)
    return found

def parse_timetable_dataframe(df: pd.DataFrame, base_config: Optional[SchoolConfig] = None) -> Tuple[TimetableProblem, List[str]]:
    """
    Parser unificato e flessibile per DataFrame pandas (da CSV o Excel).
    Riconosce qualsiasi ordine delle colonne e molteplici varianti dei nomi di intestazione.
    """
    logs = []
    
    # Normalizza i nomi delle colonne
    clean_cols = [str(c).strip().lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "_") for c in df.columns]
    
    def get_col_name(candidates: List[str]) -> Optional[str]:
        for c in candidates:
            for idx, col_clean in enumerate(clean_cols):
                if c == col_clean or c in col_clean:
                    return df.columns[idx]
        return None

    c_doc = get_col_name(["docente", "nome_docente", "insegnante", "prof"])
    c_cdc = get_col_name(["cdc", "classe_di_concorso", "concorso"])
    c_cls = get_col_name(["classe", "sezione", "classe_id"])
    c_sub = get_col_name(["materia", "disciplina", "insegnamento"])
    c_hrs = get_col_name(["ore_settimanali", "ore_settimana", "ore_sett", "ore", "monte_ore_materia"])
    c_dbl = get_col_name(["ore_doppie", "doppie", "blocco_2h", "blocco"])
    c_mda = get_col_name(["max_ore_giorno_materia", "max_giornaliere_materia", "max_ore_materia"])
    
    c_pt  = get_col_name(["part_time", "pt", "orario_ridotto"])
    c_ch  = get_col_name(["ore_contratto", "contratto", "monte_ore_docente", "ore_docente"])
    c_mwd = get_col_name(["max_giorni_presenza", "max_giorni", "giorni_presenza", "max_gg"])
    c_fds = get_col_name(["giorni_liberi", "giorno_libero", "liberi", "giorno_libero_1", "libero_1"])
    c_fd2 = get_col_name(["giorno_libero_2", "libero_2"])
    c_late = get_col_name(["entra_tardi", "tardi", "no_1a_ora", "no_1"])
    c_early = get_col_name(["esce_presto", "presto", "no_ultima_ora", "no_ult"])
    c_mdh = get_col_name(["max_ore_giorno_docente", "max_ore_giorno", "max_ore_docente"])
    c_mgh = get_col_name(["max_ore_buche", "buche", "max_gap"])
    c_sft = get_col_name(["slot_sconsigliati", "sconsigliati", "desiderata"])
    c_unv = get_col_name(["slot_indisponibili", "indisponibili", "indisponibilita"])

    if not c_doc or not c_cls or not c_sub:
        raise ValueError("Il file deve contenere almeno le colonne: 'Docente', 'Classe' e 'Materia'.")

    config = base_config or SchoolConfig(
        num_days=5,
        daily_hours=[6, 6, 6, 6, 6],
        school_name="Scuola Secondaria di I Grado",
        school_type="Secondaria I Grado (Scuola Media)"
    )

    teachers: Dict[str, Teacher] = {}
    classes: Dict[str, SchoolClass] = {}
    subjects: Dict[str, Subject] = {}
    assignments: List[TeachingAssignment] = []

    for _, row in df.iterrows():
        doc_val = str(row[c_doc]).strip() if pd.notna(row[c_doc]) else ""
        cls_val = str(row[c_cls]).strip() if pd.notna(row[c_cls]) else ""
        sub_val = str(row[c_sub]).strip() if pd.notna(row[c_sub]) else ""
        
        if not doc_val or not cls_val or not sub_val or doc_val.lower() == "nan":
            continue

        # 1. Parsing Docente
        t_id = "doc_" + _clean_id(doc_val)
        cdc_val = str(row[c_cdc]).strip() if (c_cdc and pd.notna(row[c_cdc])) else ""
        if cdc_val.lower() == "nan": cdc_val = ""
        
        if t_id not in teachers:
            is_pt = _parse_bool(row[c_pt]) if c_pt else False
            c_hours = _parse_int(row[c_ch], default=(12 if is_pt else 18)) if c_ch else (12 if is_pt else 18)
            m_days = _parse_int(row[c_mwd], default=(3 if is_pt else config.num_days)) if c_mwd else (3 if is_pt else config.num_days)
            
            f_days = []
            if c_fds and pd.notna(row[c_fds]):
                f_days.extend(_parse_free_days(row[c_fds]))
            if c_fd2 and pd.notna(row[c_fd2]):
                for fd in _parse_free_days(row[c_fd2]):
                    if fd not in f_days: f_days.append(fd)
                    
            late_val = _parse_bool(row[c_late]) if c_late else False
            early_val = _parse_bool(row[c_early]) if c_early else False
            mdh_val = _parse_int(row[c_mdh], default=5) if c_mdh else 5
            mgh_val = _parse_int(row[c_mgh], default=2) if c_mgh else 2
            
            soft_slots = _parse_slots_str(row[c_sft]) if c_sft else []
            unavail_slots = _parse_slots_str(row[c_unv]) if c_unv else []
            
            teachers[t_id] = Teacher(
                id=t_id,
                name=doc_val,
                cdc=cdc_val,
                is_part_time=is_pt,
                contract_hours=c_hours if is_pt else 18,
                max_working_days=m_days if is_pt else None,
                free_days=f_days,
                free_day_1=f_days[0] if f_days else None,
                free_day_2=f_days[1] if len(f_days) > 1 else None,
                prefer_late_entry=late_val,
                prefer_early_exit=early_val,
                max_daily_hours=mdh_val or 5,
                max_gap_hours=mgh_val if mgh_val is not None else 2,
                soft_avoid_slots=soft_slots,
                unavailable_slots=unavail_slots
            )
        else:
            if cdc_val and not teachers[t_id].cdc:
                teachers[t_id].cdc = cdc_val
            if c_sft and pd.notna(row[c_sft]):
                for s in _parse_slots_str(row[c_sft]):
                    if s not in teachers[t_id].soft_avoid_slots: teachers[t_id].soft_avoid_slots.append(s)
            if c_unv and pd.notna(row[c_unv]):
                for s in _parse_slots_str(row[c_unv]):
                    if s not in teachers[t_id].unavailable_slots: teachers[t_id].unavailable_slots.append(s)

        # 2. Parsing Classe
        c_id = _clean_id(cls_val)
        if c_id not in classes:
            grade_m = re.search(r'(\d+)', cls_val)
            grade_val = int(grade_m.group(1)) if grade_m else 1
            sec_m = re.search(r'([a-zA-Z])$', cls_val.strip())
            sec_val = sec_m.group(1).upper() if sec_m else "A"
            
            classes[c_id] = SchoolClass(
                id=c_id,
                name=cls_val,
                grade=grade_val,
                section=sec_val
            )

        # 3. Parsing Materia
        s_id = _clean_id(sub_val)
        if s_id not in subjects:
            color = DEFAULT_SUBJECT_COLORS.get(s_id, DEFAULT_SUBJECT_COLORS.get(sub_val.lower(), "#3498db"))
            subjects[s_id] = Subject(
                id=s_id,
                name=sub_val,
                color=color,
                cdc=cdc_val
            )

        # 4. Parsing Assegnazione Cattedra
        hours_val = _parse_int(row[c_hrs], default=2) if c_hrs else 2
        if hours_val <= 0: hours_val = 2
            
        double_val = _parse_bool(row[c_dbl]) if c_dbl else False
        max_daily_m = _parse_int(row[c_mda], default=2) if c_mda else 2
        
        assign_id = f"a_{c_id}_{s_id}_{t_id}_{len(assignments)}".lower()
        assignments.append(TeachingAssignment(
            id=assign_id,
            teacher_id=t_id,
            class_id=c_id,
            subject_id=s_id,
            hours_per_week=hours_val,
            force_double_hours=double_val,
            max_daily_hours=max_daily_m
        ))

    tot_ore_caricate = sum(a.hours_per_week for a in assignments)
    logs.append(f"Importati con successo: **{len(teachers)} docenti**, **{len(classes)} classi**, **{len(subjects)} materie**, **{len(assignments)} cattedre** (*Totale: **{tot_ore_caricate} ore settimanali***).")
    
    return TimetableProblem(
        config=config,
        teachers=teachers,
        classes=classes,
        subjects=subjects,
        rooms={},
        assignments=assignments
    ), logs


def parse_csv_timetable(file_content: str, base_config: Optional[SchoolConfig] = None) -> Tuple[TimetableProblem, List[str]]:
    """Legge una stringa CSV (auto-rilevando il separatore) e la converte in TimetableProblem."""
    first_line = file_content.split('\n')[0] if file_content else ""
    delimiter = ';' if ';' in first_line else (',' if ',' in first_line else '\t')
    df = pd.read_csv(io.StringIO(file_content), sep=delimiter, dtype=str)
    return parse_timetable_dataframe(df, base_config)


def parse_excel_timetable(file_bytes: bytes, base_config: Optional[SchoolConfig] = None) -> Tuple[TimetableProblem, List[str]]:
    """Legge un file Excel .xlsx in byte e lo converte in TimetableProblem."""
    df = pd.read_excel(io.BytesIO(file_bytes), dtype=str)
    return parse_timetable_dataframe(df, base_config)


# =============================================================
# MODULO RACCOLTA DESIDERATA DOCENTI (SELF-SERVICE / QUESTIONARIO)
# =============================================================
DESIDERATA_HEADERS = [
    "Docente",
    "CdC",
    "Part_Time",
    "Ore_Contratto",
    "Max_Giorni_Presenza",
    "Giorno_Libero_1",
    "Giorno_Libero_2",
    "Giorni_Entra_Tardi",
    "Giorni_Esce_Presto",
    "Max_Ore_Giorno",
    "Max_Ore_Buche",
    "Slot_Sconsigliati",
    "Slot_Indisponibili",
    "Note_Docente"
]

def generate_teacher_desiderata_form(problem: Optional[TimetableProblem] = None) -> bytes:
    """
    Genera un file Excel (.xlsx) formattato specificamente come 'Modulo Raccolta Desiderata Docenti'
    da inviare ai docenti o condividere su Google Drive / Microsoft Forms.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Desiderata Docenti"

    # Intestazione Modulo Istituzionale
    ws.merge_cells("A1:N1")
    title_cell = ws["A1"]
    school_name = problem.config.school_name if problem else "Scuola Secondaria di I Grado"
    title_cell.value = f"📝 MODULO RACCOLTA DESIDERATA PERSONALI DOCENTI — {school_name.upper()}"
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:N2")
    sub_cell = ws["A2"]
    sub_cell.value = "Istruzioni per il docente: Indicare giorni liberi (1ª/2ª scelta), giorni con preferenza entrata posticipata (No 1ª ora) o uscita anticipata (No ult. ora), e slot vietati per L.104/COE."
    sub_cell.font = Font(name="Calibri", size=10, italic=True, color="333333")
    sub_cell.fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 20

    # Header Colonne
    header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style='thin', color='BFBFBF'),
        right=Side(style='thin', color='BFBFBF'),
        top=Side(style='thin', color='BFBFBF'),
        bottom=Side(style='thin', color='BFBFBF')
    )

    for col_idx, h_text in enumerate(DESIDERATA_HEADERS, 1):
        cell = ws.cell(row=3, column=col_idx)
        cell.value = h_text
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border
    ws.row_dimensions[3].height = 28

    # Dati Docenti (o righe vuote se non presenti)
    row_num = 4
    if problem and problem.teachers:
        for t_id, t in problem.teachers.items():
            is_pt = "Si" if getattr(t, "is_part_time", False) else "No"
            ch = getattr(t, "contract_hours", 18) or 18
            max_d = getattr(t, "max_working_days", 5) if is_pt else 5
            
            f_days = getattr(t, "free_days", [])
            fd1 = f_days[0] if len(f_days) > 0 else (getattr(t, "free_day_1", "") or "")
            fd2 = f_days[1] if len(f_days) > 1 else (getattr(t, "free_day_2", "") or "")
            
            l_days = getattr(t, "late_entry_days", [])
            late_str = ", ".join(l_days) if l_days else ("Si" if getattr(t, "prefer_late_entry", False) else "No")
            
            e_days = getattr(t, "early_exit_days", [])
            early_str = ", ".join(e_days) if e_days else ("Si" if getattr(t, "prefer_early_exit", False) else "No")
            
            m_day = getattr(t, "max_daily_hours", 5) or 5
            m_gap = getattr(t, "max_gap_hours", 2) or 2
            
            # Format slots
            soft_str = ""
            if hasattr(t, "soft_avoid_slots") and t.soft_avoid_slots:
                parts = []
                for s in t.soft_avoid_slots:
                    if len(s) == 2 and s[0] < len(DAYS_OF_WEEK):
                        parts.append(f"{DAYS_OF_WEEK[s[0]]} {s[1] + 1}")
                soft_str = "; ".join(parts)
                
            unav_str = ""
            if hasattr(t, "unavailable_slots") and t.unavailable_slots:
                parts = []
                for s in t.unavailable_slots:
                    if len(s) == 2 and s[0] < len(DAYS_OF_WEEK):
                        parts.append(f"{DAYS_OF_WEEK[s[0]]} {s[1] + 1}")
                unav_str = "; ".join(parts)

            row_values = [
                t.name, getattr(t, "cdc", ""), is_pt, ch, max_d,
                fd1, fd2, late_str, early_str, m_day, m_gap, soft_str, unav_str, ""
            ]
            
            for col_idx, val in enumerate(row_values, 1):
                c = ws.cell(row=row_num, column=col_idx, value=val)
                c.alignment = Alignment(horizontal="center" if col_idx not in [1, 12, 13, 14] else "left", vertical="center")
                c.border = thin_border
            ws.row_dimensions[row_num].height = 20
            row_num += 1
    else:
        # 10 righe vuote d'esempio
        example_teachers = [
            ("Prof.ssa Bianchi", "A-22", "No", 18, 5, "Mercoledì", "", "Lunedì", "Venerdì", 5, 2, "Lunedì 1", "", "Entrata posticipata lunedì, uscita anticipata venerdì"),
            ("Prof. Romano", "A-28", "No", 18, 5, "Lunedì", "Venerdì", "Giovedì", "No", 4, 2, "", "Mercoledì 6", "Indisponibilità mercoledì 6a ora"),
            ("Prof.ssa Rossi", "A-24", "Si", 9, 3, "Lunedì", "Giovedì", "No", "No", 4, 1, "", "", "Part-time su 3 giorni"),
        ]
        for ex in example_teachers:
            row_values = list(ex) + [""]
            for col_idx, val in enumerate(row_values, 1):
                c = ws.cell(row=row_num, column=col_idx, value=val)
                c.alignment = Alignment(horizontal="center" if col_idx not in [1, 12, 13, 14] else "left", vertical="center")
                c.border = thin_border
            ws.row_dimensions[row_num].height = 20
            row_num += 1

    # Larghezza Colonne Ottimale
    col_widths = {
        "A": 26, "B": 12, "C": 12, "D": 14, "E": 20,
        "F": 18, "G": 18, "H": 14, "I": 14, "J": 15,
        "K": 15, "L": 24, "M": 24, "N": 35
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    out_io = io.BytesIO()
    wb.save(out_io)
    return out_io.getvalue()


def merge_teacher_desiderata_file(file_bytes_or_str: Any, problem: TimetableProblem, filename: str = "") -> Tuple[int, List[str]]:
    """
    Importa o fonde i desiderata compilati dai docenti (da file Excel o CSV)
    all'interno del problema corrente senza intaccare le classi o le cattedre esistenti.
    """
    logs = []
    if isinstance(file_bytes_or_str, bytes):
        if filename.lower().endswith(".csv"):
            content_str = file_bytes_or_str.decode('utf-8-sig', errors='replace')
            first_line = content_str.split('\n')[0] if content_str else ""
            delim = ';' if ';' in first_line else (',' if ',' in first_line else '\t')
            df = pd.read_csv(io.StringIO(content_str), sep=delim, dtype=str)
        else:
            # Salta le prime 2 righe se è il template formattato con titolo
            try:
                df = pd.read_excel(io.BytesIO(file_bytes_or_str), skiprows=2, dtype=str)
                # Se non ha le colonne giuste, prova a leggerlo senza skiprows
                if not any(c in str(df.columns) for c in ["Docente", "docente", "Nome"]):
                    df = pd.read_excel(io.BytesIO(file_bytes_or_str), dtype=str)
            except Exception:
                df = pd.read_excel(io.BytesIO(file_bytes_or_str), dtype=str)
    else:
        first_line = str(file_bytes_or_str).split('\n')[0] if file_bytes_or_str else ""
        delim = ';' if ';' in first_line else (',' if ',' in first_line else '\t')
        df = pd.read_csv(io.StringIO(str(file_bytes_or_str)), sep=delim, dtype=str)

    # Identifica le colonne nel dataframe caricato
    col_map = {}
    for c in df.columns:
        norm = str(c).lower().strip().replace(" ", "_").replace("-", "_")
        col_map[norm] = c

    def get_c(*keys):
        for k in keys:
            if k in col_map:
                return col_map[k]
        return None

    c_doc = get_c("docente", "nome_docente", "insegnante", "nome", "prof")
    if not c_doc:
        raise ValueError("Colonna 'Docente' non trovata nel file caricato.")

    c_cdc = get_c("cdc", "classe_di_concorso", "materia_cdc")
    c_pt = get_c("part_time", "pt", "tipo_contratto", "tempo_parziale")
    c_ch = get_c("ore_contratto", "ore", "monte_ore", "ore_settimanali")
    c_mwd = get_c("max_giorni_presenza", "max_giorni", "giorni_presenza", "giorni_max")
    c_fd1 = get_c("giorno_libero_1", "giorno_libero", "libero_1", "libero")
    c_fd2 = get_c("giorno_libero_2", "libero_2")
    c_late = get_c("giorni_entra_tardi", "entra_tardi", "no_1_ora", "no_1a_ora", "entrata_posticipata", "tardi")
    c_early = get_c("giorni_esce_presto", "esce_presto", "no_ultima_ora", "no_ult_ora", "uscita_anticipata", "presto")
    c_md = get_c("max_ore_giorno", "max_ore_giorno_docente", "max_ore_giornaliere")
    c_gap = get_c("max_ore_buche", "max_buche", "ore_buche")
    c_soft = get_c("slot_sconsigliati", "ore_sconsigliate", "sconsigliati")
    c_unav = get_c("slot_indisponibili", "indisponibilita", "indisponibili", "indisponibilita_assolute")

    num_updated = 0
    for _, row in df.iterrows():
        t_raw = str(row[c_doc]).strip()
        if not t_raw or t_raw.lower() in ["nan", "none", "docente", ""]:
            continue

        # Cerca il docente nel problema (per nome esatto o ID)
        target_teacher = None
        for t_obj in problem.teachers.values():
            if t_obj.name.lower() == t_raw.lower() or t_obj.id.lower() == t_raw.lower():
                target_teacher = t_obj
                break
        
        # Se non esiste, crealo
        if not target_teacher:
            new_id = f"doc_{t_raw.lower().replace(' ', '_').replace('.', '')}"
            target_teacher = Teacher(id=new_id, name=t_raw)
            problem.teachers[new_id] = target_teacher
            logs.append(f"Aggiunto nuovo docente: **{t_raw}**")

        # Aggiorna i desiderata
        if c_cdc and pd.notna(row[c_cdc]):
            target_teacher.cdc = str(row[c_cdc]).strip()

        if c_pt and pd.notna(row[c_pt]):
            target_teacher.is_part_time = _parse_bool(row[c_pt])

        if c_ch and pd.notna(row[c_ch]):
            target_teacher.contract_hours = _parse_int(row[c_ch], default=18)

        if c_mwd and pd.notna(row[c_mwd]):
            target_teacher.max_working_days = _parse_int(row[c_mwd], default=5)

        # Giorni liberi
        f_days = []
        if c_fds and pd.notna(row[c_fds]):
            f_days = _parse_free_days(row[c_fds])
        if c_fd1 and pd.notna(row[c_fd1]) and str(row[c_fd1]).strip() not in ["", "nan", "Nessuno"]:
            d1 = str(row[c_fd1]).strip()
            if d1 not in f_days: f_days.append(d1)
        if c_fd2 and pd.notna(row[c_fd2]) and str(row[c_fd2]).strip() not in ["", "nan", "Nessuno"]:
            d2 = str(row[c_fd2]).strip()
            if d2 not in f_days: f_days.append(d2)

        target_teacher.free_days = f_days
        target_teacher.free_day_1 = f_days[0] if len(f_days) > 0 else None
        target_teacher.free_day_2 = f_days[1] if len(f_days) > 1 else None

        if c_late and pd.notna(row[c_late]):
            l_val = str(row[c_late]).strip()
            l_days = _parse_free_days(l_val)
            target_teacher.late_entry_days = l_days
            target_teacher.prefer_late_entry = len(l_days) > 0 or _parse_bool(l_val)

        if c_early and pd.notna(row[c_early]):
            e_val = str(row[c_early]).strip()
            e_days = _parse_free_days(e_val)
            target_teacher.early_exit_days = e_days
            target_teacher.prefer_early_exit = len(e_days) > 0 or _parse_bool(e_val)

        if c_md and pd.notna(row[c_md]):
            target_teacher.max_daily_hours = _parse_int(row[c_md], default=5)

        if c_gap and pd.notna(row[c_gap]):
            target_teacher.max_gap_hours = _parse_int(row[c_gap], default=2)

        if c_soft and pd.notna(row[c_soft]):
            target_teacher.soft_avoid_slots = _parse_slots(row[c_soft])

        if c_unav and pd.notna(row[c_unav]):
            target_teacher.unavailable_slots = _parse_slots(row[c_unav])

        num_updated += 1

    logs.append(f"✅ Aggiornati i desiderata personali di **{num_updated} docenti** con successo!")
    return num_updated, logs

