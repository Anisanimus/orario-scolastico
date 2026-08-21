# 🎓 Orario Scolastico Facile

Un'applicazione intuitiva e potente per la **formulazione automatica dell'orario scolastico** per **Scuole Secondarie di I e II Grado** (Medie e Superiori), realizzata in Python con **Streamlit** e **Google OR-Tools (CP-SAT)**.

---

## 🌟 Caratteristiche Principali

- ⚙️ **Dashboard Flessibile**:
  - Settimana su **5 giorni** (settimana corta) o **6 giorni**.
  - Configurazione personalizzata delle ore giornaliere (es. 5, 6, 7 ore o rientri pomeridiani).
  - Gestione di **Aule Speciali e Laboratori** a capienza limitata (Palestre, Lab. Informatica, Lab. Scienze).

- 👥 **Docenti & Desiderata Personali**:
  - Giorno libero desiderato (1ª e 2ª scelta).
  - **Griglia di indisponibilità oraria** giorno per giorno (per docenti part-time o a scavalco con altre scuole / COE).
  - Controllo del carico massimo giornaliero e consecutivo.
  - **Minimizzazione delle ore buche** (buchi tra le lezioni).

- 🏫 **Classi & Materie**:
  - Gestione classi e sezioni.
  - Materie con colori dedicati per una visualizzazione immediata.

- 📚 **Cattedre & Desiderata Didattici**:
  - Assegnazione rapida Docente ↔ Materia ↔ Classe ↔ Monte ore.
  - **Ore Doppie / Consecutività**: vincolo per blocchi da 2 ore consecutive (compiti in classe di Lettere, laboratori, disegno tecnico, scienze motorie).
  - Monitoraggio automatico del monte ore settimanale per classe.

- 🚀 **Motore Logico OR-Tools**:
  - Risoluzione in pochi secondi con ottimizzazione matematica di tutti i vincoli rigidi e dei desiderata.
  - Report di qualità con statistiche sui giorni liberi soddisfatti e ore buche ridotte al minimo.

- 📊 **Visualizzazione & Esportazione**:
  - Vista per singola **Classe** o singolo **Docente** con evidenza di ore buche e giorni liberi.
  - Download in **Excel (.xlsx)** formattato con fogli separati per classi, docenti e quadro generale.

---

## 🚀 Come Avviare l'Applicazione

### Metodo 1: Doppio Clic (Consigliato per principianti)
Fai doppio clic sul file:
👉 **`avvia_orario.bat`**

Si aprirà automaticamente il browser all'indirizzo `http://localhost:8501`.

### Metodo 2: Da Terminale / PowerShell
Apri il terminale nella cartella del progetto ed esegui:
```powershell
python -m streamlit run app.py
```
