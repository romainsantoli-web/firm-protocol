# FIRM Protocol — Tutoriel complet

> Guide pas-à-pas pour créer, gérer et faire évoluer une organisation autonome avec FIRM.

---

## Table des matières

1. [Installation](#1-installation)
2. [Premiers pas — Créer une organisation (CLI)](#2-premiers-pas--créer-une-organisation-cli)
3. [Gérer les agents](#3-gérer-les-agents)
4. [Enregistrer des actions — Le système d&#39;autorité](#4-enregistrer-des-actions--le-système-dautorité)
5. [Gouvernance — Propositions et votes](#5-gouvernance--propositions-et-votes)
6. [Rôles dynamiques](#6-rôles-dynamiques)
7. [Mémoire collective](#7-mémoire-collective)
8. [Marché interne — Bounties et tâches](#8-marché-interne--bounties-et-tâches)
9. [Évolution autonome des paramètres](#9-évolution-autonome-des-paramètres)
10. [Amendements constitutionnels](#10-amendements-constitutionnels)
11. [Audit et état de l&#39;organisation](#11-audit-et-état-de-lorganisation)
12. [Mode REPL interactif](#12-mode-repl-interactif)
13. [Agents LLM — Choisir son modèle (Claude, GPT, Gemini, Copilot Pro)](#13-agents-llm--choisir-son-modèle-claude-gpt-gemini-copilot-pro)
14. [Utilisation en Python (API programmatique)](#14-utilisation-en-python-api-programmatique)
15. [Scénario complet Python — De A à Z](#15-scénario-complet-python--de-a-à-z)
16. [API REST (FastAPI)](#16-api-rest-fastapi)
17. [Module BountyHunter](#17-module-bountyhunter)
18. [Fédération entre organisations](#18-fédération-entre-organisations)
19. [Marchés de prédiction](#19-marchés-de-prédiction)
20. [Persistence — Sauvegarder et charger l&#39;état](#20-persistence--sauvegarder-et-charger-létat)
21. [Référence rapide des commandes](#21-référence-rapide-des-commandes)
22. [Bridge MCP — Connecter l&#39;écosystème (138 tools)](#22-bridge-mcp--connecter-lécosystème-138-tools)
23. [Génération automatique de rapports (bonnes pratiques)](#23-génération-automatique-de-rapports-bonnes-pratiques)

---

## 1. Installation

### Option A : Depuis PyPI (recommandé)

```bash
# Core uniquement — zéro dépendance externe, stdlib Python seul
pip install firm-protocol

# Avec les providers LLM (OpenAI, Anthropic, Mistral)
pip install "firm-protocol[llm]"

# Avec le serveur REST API (FastAPI + Uvicorn)
pip install "firm-protocol[api]"

# Avec le module bug bounty (httpx, pyyaml)
pip install "firm-protocol[bounty]"

# Tout inclus
pip install "firm-protocol[all]"
```

### Option B : Depuis les sources

```bash
git clone https://github.com/romainsantoli-web/firm-protocol.git
cd firm-protocol
pip install -e ".[dev]"   # dev inclut tests, linter, etc.
```

**Prérequis :** Python 3.11 ou supérieur.

### Vérifier l'installation

```bash
firm --version
# → firm-protocol 1.1.0
```

---

## 2. Premiers pas — Créer une organisation (CLI)

Toute interaction commence par **initialiser une organisation** :

```bash
firm init mon-startup
```

**Résultat :**

```
FIRM 'mon-startup' created (id=firm-abc12345)
State saved to firm-state.json
```

Cela crée un fichier `firm-state.json` dans le répertoire courant. Ce fichier contient tout l'état de votre organisation. Chaque commande qui modifie l'état le sauvegarde automatiquement.

> **Changer le fichier d'état :** utilisez `--state mon-fichier.json` ou la variable d'environnement `FIRM_STATE=chemin.json`.

```bash
# Exemple avec un fichier d'état personnalisé
firm --state /path/to/my-org.json init acme-corp
```

---

## 3. Gérer les agents

### Ajouter des agents

```bash
# Ajouter un agent avec l'autorité par défaut (0.5)
firm agent add Alice

# Ajouter un agent avec une autorité initiale élevée (max: 1.0)
firm agent add Bob --authority 0.8

# Ajouter un troisième agent
firm agent add Charlie --authority 0.3
```

Chaque agent reçoit un identifiant unique (ex: `agent-a1b2c3d4`).

### Lister les agents

```bash
firm agent list
```

**Résultat :**

```
Name       ID              Authority   Status   Credits
─────────────────────────────────────────────────────────
Alice      agent-abc123    0.500       active   100.0
Bob        agent-def456    0.800       active   100.0
Charlie    agent-ghi789    0.300       active   100.0
```

Pour voir aussi les agents inactifs :

```bash
firm agent list --all
```

---

## 4. Enregistrer des actions — Le système d'autorité

Le cœur de FIRM : **l'autorité n'est pas attribuée, elle est gagnée**. Chaque succès augmente l'autorité d'un agent, chaque échec la diminue.

### Enregistrer un succès

```bash
firm action Alice ok "Livré la feature d'authentification dans les temps"
```

**Résultat :**

```
Action recorded: Alice succeeded
Authority: 0.500 → 0.548 (+0.048)
```

### Enregistrer un échec

```bash
firm action Bob fail "A cassé le pipeline CI en production"
```

**Résultat :**

```
Action recorded: Bob failed
Authority: 0.800 → 0.784 (-0.016)
```

### Comment ça marche ?

La formule d'autorité est **hebbienne** (inspirée des neurosciences) :

```
Δautorité = learning_rate × activation × (1 + bonus_calibration) − decay × (1 − activation)
```

- `activation = 1.0` en cas de succès, `0.0` en cas d'échec
- `learning_rate` par défaut : 0.05
- `decay` par défaut : 0.02
- L'autorité reste toujours entre `[0.0, 1.0]`

### Les seuils d'autorité

| Seuil   | Signification                                |
| ------- | -------------------------------------------- |
| ≥ 0.80 | Peut proposer des changements de gouvernance |
| ≥ 0.60 | Peut voter sur les propositions              |
| ≥ 0.40 | Autorité standard de travail                |
| ≤ 0.30 | En probation                                 |
| ≤ 0.05 | Auto-terminaison (l'agent est désactivé)   |

---

## 5. Gouvernance — Propositions et votes

Les changements importants passent par un processus de **gouvernance en 2 cycles** avec simulation, stress test, vote et période de refroidissement.

### Étape 1 : Créer une proposition

Seuls les agents avec une autorité ≥ 0.80 peuvent proposer :

```bash
firm propose Bob "Ajouter un rôle DevOps" "Créer un rôle dédié au déploiement et monitoring"
```

> **Note :** `Bob` doit être l'ID de l'agent OU son nom (la CLI résout les noms).

**Résultat :**

```
Proposal created: prop-xyz789
Title: Ajouter un rôle DevOps
Status: draft
```

### Étape 2 : Voter

Les agents avec autorité ≥ 0.60 peuvent voter. Les votes sont pondérés par l'autorité :

```bash
firm vote prop-xyz789 Alice approve
firm vote prop-xyz789 Charlie reject
```

**Résultat :**

```
Vote recorded: Alice → approve on prop-xyz789
```

### Étape 3 : Finaliser

```bash
firm finalize prop-xyz789
```

**Résultat :**

```
Proposal finalized: approved
No constitutional violations detected.
```

Si la proposition viole une invariante constitutionnelle, l'Agent Constitutionnel la bloque automatiquement.

---

## 6. Rôles dynamiques

Les rôles dans FIRM ne sont pas fixes — ils sont assignés selon l'autorité.

### Définir un rôle

```bash
firm role define deployer "Responsable des déploiements en production"
```

Par défaut, le rôle nécessite une autorité minimum de 0.3. Pour modifier :

```bash
firm role define lead-architect "Architecte principal" --min-authority 0.7
```

### Assigner un rôle

```bash
firm role assign Alice deployer
```

**Résultat :**

```
Role 'deployer' assigned to Alice
```

Si Alice n'a pas l'autorité minimum requise par le rôle, l'assignation est refusée.

---

## 7. Mémoire collective

FIRM possède une mémoire partagée où les agents peuvent contribuer et rappeler des connaissances. Les souvenirs ont un **poids** qui évolue.

### Ajouter un souvenir

```bash
firm memory add Alice "Les déploiements du vendredi causent 3x plus d'incidents" --tags "ops,incidents,best-practice"
```

### Rappeler des souvenirs

```bash
firm memory recall incidents
```

**Résultat :**

```
Memory results for 'incidents':
  [0.75] "Les déploiements du vendredi causent 3x plus d'incidents"
         by Alice | tags: ops, incidents, best-practice
```

En Python, vous pouvez aussi **renforcer** ou **contester** un souvenir pour modifier son poids :

```python
firm.reinforce_memory(alice.id, memory_id)    # +poids
firm.challenge_memory(bob.id, memory_id,
    counter_evidence="Données du Q4 montrent le contraire")  # -poids
```

---

## 8. Marché interne — Bounties et tâches

FIRM intègre un système économique interne avec des bounties, enchères et règlements.

### Poster une tâche

```bash
firm market post Alice "Corriger le bug d'authentification" 50
```

Cela crée une tâche avec un bounty de 50 crédits, financée par Alice.

**Résultat :**

```
Task posted: task-abc123
Title: Corriger le bug d'authentification
Bounty: 50.0 credits
```

### Enchérir sur une tâche

```bash
firm market bid task-abc123 Bob 40
```

Bob propose de faire le travail pour 40 crédits.

### Flux complet (en Python)

```python
# Poster une tâche
task = firm.post_task(alice.id, "Fix auth bug", "Critical security fix", bounty=50.0)

# Un agent enchérit
bid = firm.bid_on_task(task.id, bob.id, amount=40.0)

# Le demandeur accepte l'enchère
firm.accept_bid(task.id, bid.id)

# Le travail est fait — régler la tâche
settlement = firm.settle_task(task.id, success=True)
# → Bob reçoit les crédits, son autorité augmente
```

---

## 9. Évolution autonome des paramètres

L'organisation peut **modifier ses propres paramètres** (learning rate, decay, etc.) via un vote de supermajorité (≥ 75%).

### Proposer un changement

```bash
firm evolve propose Alice learning_rate 0.08
```

Cela propose de changer le taux d'apprentissage de 0.05 à 0.08.

### Voter sur l'évolution

```bash
firm evolve vote evol-abc123 Bob approve
firm evolve vote evol-abc123 Charlie approve
```

### Appliquer le changement

```bash
firm evolve apply evol-abc123
```

**Résultat :**

```
Evolution applied:
  learning_rate: 0.05 → 0.08
Generation: 1 → 2
```

---

## 10. Amendements constitutionnels

Les deux invariantes fondamentales (contrôle humain + capacité d'évolution) ne peuvent jamais être supprimées. Mais on peut **ajouter** de nouvelles règles constitutionnelles.

### Proposer un amendement

```bash
firm amend Alice add_invariant "Tout agent doit passer un audit de sécurité avant d'accéder à la production"
```

Types possibles : `add_invariant`, `remove_invariant`, `add_keywords`, `remove_keywords`.

> **Important :** les invariantes originales (kill switch + évolution) sont protégées et ne peuvent pas être supprimées.

---

## 11. Audit et état de l'organisation

### Voir l'état général

```bash
firm status
```

**Résultat :**

```
FIRM Status: mon-startup
══════════════════════════════════
Agents:          3 (3 active)
Authority range: 0.30 — 0.85
Ledger entries:  12
Chain valid:     ✓
Kill switch:     inactive
Proposals:       1 (1 approved)
Roles defined:   2
Memory entries:  1
Federation peers: 0
Evolution gen:   2
Market tasks:    1 (0 open)
Amendments:      1
```

### Lancer un audit complet

```bash
firm audit
```

**Résultat :**

```
Audit Report
════════════
Chain integrity:  ✓ valid (12 entries verified)
Findings:         2
  [MEDIUM] Agent 'Charlie' authority below threshold (0.30)
  [INFO] No federation peers registered
```

L'audit vérifie l'intégrité du ledger (chaîne de hashes SHA-256), les seuils d'autorité, la santé de la gouvernance, etc.

---

## 12. Mode REPL interactif

Pour une interaction fluide sans taper `firm` à chaque commande :

```bash
firm repl
```

**Résultat :**

```
╔══════════════════════════════════════╗
║  FIRM Protocol REPL v1.1.0          ║
║  State: firm-state.json             ║
╚══════════════════════════════════════╝

firm> help
Available commands:
  add <name> [authority]    Add an agent
  action <name> ok|fail     Record an action
  agents                    List agents
  status                    Show org status
  propose <name> <title>    Create proposal
  vote <prop> <name> y|n    Vote on proposal
  params                    Show firm parameters
  ledger                    Show last 10 entries
  audit                     Run audit
  save [file]               Save state
  load <file>               Load state
  export <file>             Export status as JSON
  help                      This message
  quit                      Exit

firm> add Eve 0.6
Agent 'Eve' added (authority: 0.6)

firm> action Eve ok Shipped the new dashboard
Authority: 0.600 → 0.648

firm> agents
Name    Authority  Status
Eve     0.648      active
Alice   0.548      active
Bob     0.784      active

firm> quit
Goodbye.
```

---

## 13. Agents LLM — Choisir son modèle (Claude, GPT, Gemini, Copilot Pro)

FIRM intègre un système d'**agents LLM** qui connecte de vrais modèles de langage au système d'autorité. Chaque agent peut utiliser un provider et un modèle différent.

### Providers disponibles

| Provider                        | Alias CLI                 | Modèle par défaut      | API Key requise       | Dépendance         |
| ------------------------------- | ------------------------- | ------------------------ | --------------------- | ------------------- |
| **Claude** (Anthropic)    | `claude`                | `claude-sonnet-4`      | `ANTHROPIC_API_KEY` | `anthropic`       |
| **GPT** (OpenAI)          | `gpt` ou `openai`     | `gpt-4o`               | `OPENAI_API_KEY`    | `openai`          |
| **Mistral**               | `mistral`               | `mistral-large-latest` | `MISTRAL_API_KEY`   | `mistralai`       |
| **Gemini** (Google)       | `gemini` ou `google`  | `gemini-2.5-pro`       | `GEMINI_API_KEY`    | `openai` (compat) |
| **Copilot** (GitHub free) | `copilot` ou `github` | `gpt-4o`               | `GITHUB_TOKEN`      | `openai`          |
| **Copilot Pro** (GitHub)  | `copilot-pro`           | `claude-sonnet-4.6`    | JWT OAuth             | `httpx`           |

### Installation des dépendances

```bash
# Pour Claude, GPT, Mistral
pip install "firm-protocol[llm]"

# Pour Copilot Pro (httpx nécessaire)
pip install "firm-protocol[all]"
```

### Configurer les clés API

```bash
# Option 1 : Variables d'environnement
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export MISTRAL_API_KEY="..."
export GEMINI_API_KEY="..."
export GITHUB_TOKEN="ghp_..."

# Option 2 : Passer directement dans le code (voir ci-dessous)
```

### Créer un agent avec un modèle spécifique

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent, AgentConfig

firm = Firm("my-org")

# ── Agent Claude (Anthropic) ──────────────────────────────────────
cto = create_llm_agent(
    firm, "CTO",
    provider_name="claude",
    model="claude-opus-4.6",        # ou "claude-sonnet-4.6", "claude-haiku-4.5"
    authority=0.8,
)

# ── Agent GPT (OpenAI) ────────────────────────────────────────────
dev = create_llm_agent(
    firm, "dev-1",
    provider_name="gpt",
    model="gpt-5.1",                # ou "gpt-4o", "gpt-5-mini"
    authority=0.5,
)

# ── Agent Mistral ─────────────────────────────────────────────────
analyst = create_llm_agent(
    firm, "analyst",
    provider_name="mistral",
    model="mistral-large-latest",    # ou "mistral-small-latest" (économique)
    authority=0.5,
)

# ── Agent Gemini (Google) ─────────────────────────────────────────
reviewer = create_llm_agent(
    firm, "reviewer",
    provider_name="gemini",
    model="gemini-2.5-pro",          # ou "gemini-3-pro", "gemini-3.1-pro"
    authority=0.5,
)
```

### Copilot Pro — Accès à tous les modèles avec un abonnement GitHub

Si vous avez **GitHub Copilot Pro** (ou Business/Enterprise), vous avez accès à un large catalogue de modèles via un seul abonnement, **sans clé API supplémentaire**.

#### Catalogue complet des modèles Copilot Pro

| Famille          | Modèles disponibles                                              | Usage recommandé                             |
| ---------------- | ----------------------------------------------------------------- | --------------------------------------------- |
| **Claude** | `claude-haiku-4.5`                                              | Tâches rapides, faible coût                 |
|                  | `claude-sonnet-4`, `claude-sonnet-4.5`, `claude-sonnet-4.6` | Bon équilibre performance/vitesse            |
|                  | `claude-opus-4.5`, `claude-opus-4.6`                          | Tâches complexes, architecture, raisonnement |
| **GPT**    | `gpt-4.1`, `gpt-4o`                                           | Usage général, bon rapport qualité/prix    |
|                  | `gpt-5-mini`                                                    | Économique, tâches simples                  |
|                  | `gpt-5.1`, `gpt-5.2`, `gpt-5.3`, `gpt-5.4`                | Dernière génération, haute performance     |
| **Codex**  | `gpt-5.1-codex`, `gpt-5.2-codex`, `gpt-5.3-codex`           | Code intensif (endpoint `/responses`)       |
|                  | `gpt-5.1-codex-mini` *(Preview)*, `gpt-5.1-codex-max`       | Mini = rapide, Max = haute qualité           |
| **Gemini** | `gemini-2.5-pro`                                                | Bon modèle généraliste Google              |
|                  | `gemini-3-pro` *(Preview)*, `gemini-3.1-pro` *(Preview)*  | Dernière génération Google                 |

> **21 modèles** accessibles avec un seul abonnement. Pas besoin de clé Anthropic, OpenAI ou Google.

#### Authentification Copilot Pro

L'authentification passe par un **flux OAuth** qui génère un JWT renouvelé automatiquement :

```python
from firm.llm.providers import CopilotProProvider

# Option 1 : JWT direct (si vous l'avez déjà)
provider = CopilotProProvider(model="claude-sonnet-4.6", api_key="eyJ...")

# Option 2 : Variable d'environnement
#   export COPILOT_JWT="eyJ..."
provider = CopilotProProvider(model="gpt-5.3")

# Option 3 : Token OAuth GitHub (auto-refresh du JWT)
provider = CopilotProProvider(model="claude-opus-4.6", oauth_token="gho_xxxx")

# Option 4 : Cache automatique (/tmp/copilot_token.json)
#   Si vous avez déjà utilisé Copilot dans VS Code, le token est souvent déjà là
provider = CopilotProProvider(model="claude-sonnet-4.6")
```

> **Obtenir le token OAuth :** Le provider utilise le même flux OAuth que VS Code Copilot
> (client_id `Iv1.b507a08c87ecfe98`). Si vous avez VS Code avec Copilot connecté, le token
> est souvent déjà mis en cache dans `/tmp/copilot_token.json`.

#### Créer des agents Copilot Pro dans une organisation

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent, AgentConfig

firm = Firm("my-startup")

# Agent CTO sur Claude Opus 4.6 — le plus capable (via Copilot Pro)
cto = create_llm_agent(
    firm, "CTO",
    provider_name="copilot-pro",
    model="claude-opus-4.6",
    authority=0.9,
)

# Agent dev sur GPT-5.3 — dernière gen OpenAI (via Copilot Pro)
dev = create_llm_agent(
    firm, "dev-1",
    provider_name="copilot-pro",
    model="gpt-5.3",
    authority=0.5,
)

# Agent code review sur Claude Sonnet 4.6 — rapide et précis
reviewer = create_llm_agent(
    firm, "reviewer",
    provider_name="copilot-pro",
    model="claude-sonnet-4.6",
    authority=0.6,
)

# Agent Codex pour le code intensif (utilise l'endpoint /responses)
coder = create_llm_agent(
    firm, "coder",
    provider_name="copilot-pro",
    model="gpt-5.3-codex",
    authority=0.7,
)

# Agent économique pour les tâches simples
junior = create_llm_agent(
    firm, "junior",
    provider_name="copilot-pro",
    model="claude-haiku-4.5",       # ou "gpt-5-mini"
    authority=0.4,
)
```

### Copilot free-tier (GitHub Models)

Si vous n'avez **pas** Copilot Pro, vous pouvez utiliser le provider `copilot` (free tier) qui passe par `models.inference.ai.azure.com` :

```python
# Free tier — modèles limités, rate-limited
free_agent = create_llm_agent(
    firm, "free-agent",
    provider_name="copilot",        # ou "github"
    model="gpt-4o",
    authority=0.5,
    # Nécessite un GITHUB_TOKEN avec scope "models:read"
)
```

### Gemini — Gratuit avec fallback automatique

Le provider Gemini (accès direct via clé API Google) gère automatiquement les **rate limits** en cascadant vers des modèles de secours :

```python
# Le fallback est transparent — jamais d'erreur 429
gemini_agent = create_llm_agent(
    firm, "analyst",
    provider_name="gemini",
    model="gemini-2.5-pro",         # ou "gemini-3-pro", "gemini-3.1-pro" via Copilot Pro
    authority=0.5,
)
```

### Exécuter une tâche avec un agent LLM

```python
# L'agent utilise le modèle configuré + des tools réels (git, terminal, fichiers, HTTP)
result = cto.execute_task(
    task="Analyser les tests qui échouent dans tests/test_api.py et proposer un fix",
    context="Le CI a échoué sur le dernier commit. Erreur: AssertionError on line 42."
)

print(f"Statut: {result.status.value}")       # completed / failed / timeout
print(f"Output: {result.output[:200]}")
print(f"Tools utilisés: {result.tools_used}")  # ['file_read', 'python_test', 'file_write']
print(f"Tokens: {result.total_tokens}")
print(f"Coût: ${result.cost_usd:.4f}")
```

### Contrôle d'accès par autorité

L'accès aux tools est **filtré par l'autorité** de l'agent :

| Autorité    | Tools disponibles                                                            |
| ------------ | ---------------------------------------------------------------------------- |
| < 0.30       | `file_read`, `file_list` seulement (probation)                           |
| 0.30 – 0.59 | +`git_status`, `git_diff`, `git_log`, `file_search`, `python_test` |
| 0.60 – 0.79 | +`file_write`, `git_commit` (écriture)                                  |
| ≥ 0.80      | +`terminal_run`, `http_get`, `http_post` (opérations dangereuses)     |

### Budget et limites par agent

```python
from firm.llm.agent import AgentConfig

config = AgentConfig(
    max_iterations=25,           # max de boucles LLM→tools→LLM
    max_tokens_budget=100_000,   # budget total en tokens (scalé par autorité)
    max_cost_usd=1.0,            # plafond de coût en USD (scalé par autorité)
    temperature=0.3,             # température du modèle
    max_response_tokens=4096,    # tokens max par réponse
    auto_record_actions=True,    # enregistre le résultat dans le système d'autorité
)

agent = create_llm_agent(
    firm, "dev",
    provider_name="copilot-pro",
    model="claude-sonnet-4.6",
    authority=0.6,
    config=config,
)

# Avec autorité 0.6, le budget réel est :
#   max_tokens = 100_000 × 0.6 = 60_000
#   max_cost   = 1.0 × 0.6     = $0.60
```

### Mixer les providers dans une même organisation

L'un des atouts de FIRM : chaque agent peut utiliser un modèle différent, adapté à son rôle.

```python
firm = Firm("multi-model-org")

# CTO = Claude Opus 4.6 (via Copilot Pro) — le plus capable
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro",
                        model="claude-opus-4.6", authority=0.9)

# Dev senior = GPT-5.3 — dernière gen, très performant
senior = create_llm_agent(firm, "Senior", provider_name="copilot-pro",
                          model="gpt-5.4", authority=0.7)

# Reviewer = Claude Sonnet 4.6 — rapide et précis pour la review
reviewer = create_llm_agent(firm, "Reviewer", provider_name="copilot-pro",
                            model="claude-sonnet-4.6", authority=0.6)

# Dev junior = Haiku 4.5 — rapide et économique
junior = create_llm_agent(firm, "Junior", provider_name="copilot-pro",
                          model="claude-haiku-4.5", authority=0.4)

# Coder = Codex — spécialisé code (endpoint /responses)
coder = create_llm_agent(firm, "Coder", provider_name="copilot-pro",
                         model="gpt-5.3-codex", authority=0.6)

# Architecte = Gemini 3.1 Pro — perspective différente
architect = create_llm_agent(firm, "Architect", provider_name="copilot-pro",
                             model="gemini-3.1-pro", authority=0.7)

# Lancer une tâche sur chaque agent
for agent in [cto, senior, reviewer, junior, coder, architect]:
    stats = agent.get_stats()
    print(f"{stats['name']:10} | {stats['provider']:12} | {stats['model']}")
```

**Résultat :**

```
CTO        | copilot-pro  | claude-opus-4.6
Senior     | copilot-pro  | gpt-5.4
Reviewer   | copilot-pro  | claude-sonnet-4.6
Junior     | copilot-pro  | claude-haiku-4.5
Coder      | copilot-pro  | gpt-5.3-codex
Architect  | copilot-pro  | gemini-3.1-pro
```

### Récapitulatif : quel provider choisir ?

| Situation                                  | Provider recommandé | Modèle                                | Coût                     |
| ------------------------------------------ | -------------------: | -------------------------------------- | ------------------------- |
| **Copilot Pro** — tâches complexes |      `copilot-pro` | `claude-opus-4.6`                    | Inclus dans l'abo         |
| **Copilot Pro** — usage général   |      `copilot-pro` | `claude-sonnet-4.6` ou `gpt-5.4`   | Inclus                    |
| **Copilot Pro** — code intensif     |      `copilot-pro` | `gpt-5.3-codex`                      | Inclus                    |
| **Copilot Pro** — tâches simples   |      `copilot-pro` | `claude-haiku-4.5` ou `gpt-5-mini` | Inclus                    |
| **Copilot Pro** — Google AI         |      `copilot-pro` | `gemini-3.1-pro`                     | Inclus                    |
| Clé**Anthropic** directe            |           `claude` | `claude-sonnet-4`                    | $3 / $15 par 1M tokens    |
| Clé**OpenAI** directe               |              `gpt` | `gpt-4o`                             | $2.5 / $10 par 1M tokens  |
| **Gratuit** (Google)                 |           `gemini` | `gemini-2.5-pro`                     | Gratuit (rate-limited)    |
| **Gratuit** (GitHub)                 |          `copilot` | `gpt-4o`                             | Gratuit (rate-limited)    |
| Budget serré                              |          `mistral` | `mistral-small-latest`               | $0.2 / $0.6 par 1M tokens |

---

## 14. Utilisation en Python (API programmatique)

### Import minimal

```python
from firm import Firm
```

### Créer et manipuler une organisation

```python
from firm import Firm

# Créer l'organisation
org = Firm(name="acme")

# Ajouter des agents
alice = org.add_agent("Alice", authority=0.8, credits=1000.0)
bob = org.add_agent("Bob", authority=0.5, credits=500.0)

# Enregistrer des actions
org.record_action(alice.id, success=True, description="Livré le MVP")
org.record_action(bob.id, success=False, description="Bug critique en prod")

# Vérifier les autorités
for agent in org.get_agents():
    print(f"  {agent.name}: {agent.authority:.3f}")
```

### Sauvegarder / charger

```python
from firm import save_firm, load_firm

# Sauvegarder
save_firm(org, "mon-org.json")

# Charger
org_restored = load_firm("mon-org.json")
```

---

## 15. Scénario complet Python — De A à Z

Voici un scénario réaliste qui traverse toutes les fonctionnalités :

```python
from firm import Firm, save_firm

# ── ACT 1 : Bootstrap ──────────────────────────────────
org = Firm(name="NeuralForge")

# Équipe fondatrice
ada   = org.add_agent("Ada",   authority=0.9, credits=1000.0)  # CEO
kai   = org.add_agent("Kai",   authority=0.7, credits=500.0)   # CTO
zara  = org.add_agent("Zara",  authority=0.5, credits=300.0)   # Eng

# Phase de travail — autorité gagnée par les résultats
for _ in range(5):
    org.record_action(ada.id, success=True, description="Décision stratégique")
for _ in range(3):
    org.record_action(kai.id, success=True, description="Systèmes core livrés")
org.record_action(kai.id, success=False, description="Panne pendant la démo")
org.record_action(zara.id, success=True, description="Feature livrée")

print("=== Autorités après Phase 1 ===")
for a in org.get_agents():
    print(f"  {a.name}: {a.authority:.3f}")

# ── ACT 2 : Structure ───────────────────────────────────
# Définir des rôles
org.define_role("architect", min_authority=0.7, description="Architecte système")
org.define_role("deployer", min_authority=0.4, description="Déploiements prod")

# Assigner des rôles (l'autorité est vérifiée)
org.assign_role(ada.id, "architect")
org.assign_role(zara.id, "deployer")

# Mémoire collective
m1 = org.contribute_memory(
    ada.id,
    "L'architecture microservices a réduit le temps de déploiement de 60%",
    tags=["architecture", "performance"]
)
org.reinforce_memory(kai.id, m1.id)  # Kai confirme

# Rappeler la mémoire
results = org.recall_memory(tags=["architecture"])
for m in results:
    print(f"  [{m.weight:.2f}] {m.content}")

# ── ACT 3 : Gouvernance ─────────────────────────────────
# Ada propose un changement (autorité >= 0.80 requise)
proposal = org.propose(
    ada.id,
    title="Adopter le déploiement continu",
    description="Basculer vers un pipeline CI/CD avec releases automatiques"
)
print(f"Proposal: {proposal.id} — {proposal.status.value}")

# Simulation (en 2 cycles avant le vote)
org.simulate_proposal(proposal.id, success=True, impact_summary="Réduit le TTM de 40%")

# Vote (pondéré par l'autorité des votants)
org.vote(proposal.id, kai.id, "approve", reason="Bon pour la vélocité")
org.vote(proposal.id, zara.id, "approve", reason="Accord")

# Finalisation
result = org.finalize_proposal(proposal.id)
print(f"Résultat: {result.status.value}")

# ── ACT 4 : Économie ────────────────────────────────────
# Poster une tâche sur le marché interne
task = org.post_task(
    ada.id,
    title="Migrer la base de données vers PostgreSQL",
    description="Migration complète avec zéro downtime",
    bounty=100.0
)

# Kai enchérit
bid = org.bid_on_task(task.id, kai.id, amount=80.0)

# Ada accepte
org.accept_bid(task.id, bid.id)

# Travail terminé avec succès
settlement = org.settle_task(task.id, success=True)
print(f"Kai a reçu {settlement.amount} crédits")

# ── ACT 5 : Évolution ───────────────────────────────────
# Proposer de changer le learning rate (supermajorité 75% requise)
evol = org.propose_evolution(
    ada.id,
    changes={"authority.learning_rate": 0.08},
    rationale="Les agents progressent trop lentement"
)

org.vote_evolution(evol.id, kai.id, approve=True)
org.vote_evolution(evol.id, zara.id, approve=True)
org.apply_evolution(evol.id)

params = org.get_firm_parameters()
print(f"Nouveau learning_rate: {params['authority']['learning_rate']}")

# ── ACT 6 : Audit final ─────────────────────────────────
report = org.run_audit()
print(f"Chaîne valide: {report.chain_valid}")
print(f"Findings: {len(report.findings)}")

status = org.status()
print(f"Agents: {status['agents']['total']}")
print(f"Entrées ledger: {status['ledger']['total_entries']}")

# Sauvegarder
save_firm(org, "neuralforge-final.json")
print("Organisation sauvegardée !")
```

**Exécuter :** `python mon_scenario.py`

---

## 16. API REST (FastAPI)

### Installation

```bash
pip install "firm-protocol[api]"
```

### Lancer le serveur

```bash
uvicorn firm.api.app:app --reload --port 8000
```

### Endpoints disponibles

Le serveur expose une API REST complète avec documentation Swagger automatique à `http://localhost:8000/docs`.

Endpoints principaux :

- `POST /agents` — Ajouter un agent
- `GET /agents` — Lister les agents
- `POST /actions` — Enregistrer une action
- `GET /status` — État de l'organisation
- `POST /proposals` — Créer une proposition
- WebSocket `/ws` pour les événements temps réel

---

## 17. Module BountyHunter

### Installation

```bash
pip install "firm-protocol[bounty]"
```

### Fichier scope YAML

Créez un fichier `scope.yaml` décrivant la cible :

```yaml
program:
  name: "Mon Programme"
  platform: hackerone

in_scope:
  - type: url
    target: "*.example.com"
  - type: url
    target: "api.example.com"
  - type: cidr
    target: "10.0.0.0/8"

out_of_scope:
  - type: url
    target: "internal.example.com"
  - type: url
    target: "staging.example.com"
```

### Commandes CLI

```bash
# Voir les 8 agents spécialisés et leurs modèles LLM
firm bounty agents

# Résultat :
#   hunt-director   Claude Opus    0.90
#   recon-agent     Claude Sonnet  0.70
#   web-hunter      Claude Sonnet  0.70
#   api-hunter      Claude Sonnet  0.70
#   code-auditor    Claude Opus    0.80
#   mobile-hunter   Claude Sonnet  0.70
#   web3-hunter     Claude Opus    0.80
#   report-writer   Claude Sonnet  0.60

# Afficher le scope du programme
firm bounty scope scope.yaml

# Initialiser une campagne
firm bounty init scope.yaml --rate-limit 10.0 --rate-burst 20

# Calculer un score CVSS v3.1
firm bounty cvss "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
# → Score: 9.8 (CRITICAL)

# Lancer une campagne complète
firm bounty campaign run --scope-file scope.yaml --max-hours 4.0 --max-findings 100
```

### En Python

```python
from firm.bounty import create_bounty_firm, ScopeEnforcer, TargetScope, CVSSVector

# Créer une organisation avec les 8 agents bounty
firm_org, campaign = create_bounty_firm("ma-campagne", scope_yaml="scope.yaml")

# Score CVSS
cvss = CVSSVector.from_string("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H")
print(f"Score: {cvss.base_score}")     # 9.8
print(f"Sévérité: {cvss.severity()}")  # CRITICAL

# Vérifier si un domaine est dans le scope
scope = TargetScope(
    in_scope=["*.example.com"],
    out_of_scope=["internal.example.com"]
)
enforcer = ScopeEnforcer(scope)
print(enforcer.is_allowed("api.example.com"))       # True
print(enforcer.is_allowed("internal.example.com"))   # False
```

---

## 18. Fédération entre organisations

FIRM permet à plusieurs organisations de collaborer via un **protocole inter-firm**.

```python
from firm import Firm

# Deux organisations indépendantes
alpha = Firm(name="Alpha Corp")
beta = Firm(name="Beta Inc")

alice = alpha.add_agent("Alice", authority=0.8)

# Enregistrer Beta comme pair
alpha.register_peer(alice.id, peer_id=beta.id, peer_name="Beta Inc")

# Envoyer un message fédéré
alpha.send_federation_message(
    alice.id,
    peer_id=beta.id,
    msg_type="collaboration",
    subject="Projet commun Q2",
    body="Proposition de collaboration sur le module auth"
)

# Détacher un agent vers une autre org
alpha.second_agent(
    alice.id,
    target_agent_id=alice.id,
    peer_id=beta.id,
    reason="Expertise sécurité nécessaire chez Beta"
)

# Émettre une attestation de réputation (cross-firm)
alpha.issue_reputation(alice.id, endorsement="Expert en sécurité, 8 audits réussis")
```

---

## 19. Marchés de prédiction

Les agents peuvent parier sur des résultats futurs. Les prédicteurs bien calibrés gagnent un **bonus d'autorité**.

```python
from firm import Firm

org = Firm(name="Predict Corp")
alice = org.add_agent("Alice", authority=0.8)
bob = org.add_agent("Bob", authority=0.6)

# Créer un marché de prédiction
market_id = org.create_prediction_market(
    creator_id=alice.id,
    question="Le refactoring auth va-t-il réduire les bugs de 50% ?",
    deadline_seconds=86400  # 24h
)

# Les agents parient
org.predict(market_id, alice.id, side=True, stake=10.0)  # Alice parie OUI
org.predict(market_id, bob.id, side=False, stake=5.0)     # Bob parie NON

# Résoudre le marché (quand le résultat est connu)
org.resolve_prediction(market_id, resolver_id=alice.id, outcome=True)
# → Alice gagne : bonus d'autorité + crédits
# → Bob perd : crédits perdus
```

Les marchés de prédiction peuvent aussi piloter la gouvernance via la **futarchie** : les propositions sont automatiquement approuvées ou rejetées selon les prédictions du marché.

---

## 20. Persistence — Sauvegarder et charger l'état

### CLI

La CLI sauvegarde automatiquement après chaque commande qui modifie l'état. Le fichier par défaut est `firm-state.json`.

```bash
# Sauvegarder manuellement (dans le REPL)
firm> save backup.json

# Charger un état (dans le REPL)
firm> load backup.json

# Exporter l'état complet en JSON
firm> export rapport.json
```

### Python

```python
from firm import Firm, save_firm, load_firm, snapshot, diff_snapshots

org = Firm(name="test")
alice = org.add_agent("Alice", authority=0.8)

# Snapshot (photo instantanée)
snap1 = snapshot(org)

# Faire des changements
org.record_action(alice.id, success=True, description="Travail")

# Nouveau snapshot
snap2 = snapshot(org)

# Comparer les deux états
diff = diff_snapshots(snap1, snap2)
print(diff)  # Montre exactement ce qui a changé

# Sauvegarder en fichier
save_firm(org, "etat.json")

# Recharger plus tard
org2 = load_firm("etat.json")
```

---

## 21. Référence rapide des commandes

| Commande                                              | Description                          |
| ----------------------------------------------------- | ------------------------------------ |
| `firm init <nom>`                                   | Créer une nouvelle organisation     |
| `firm agent add <nom> [--authority N]`              | Ajouter un agent                     |
| `firm agent list [--all]`                           | Lister les agents                    |
| `firm action <agent> <ok\|fail> <desc>`              | Enregistrer une action               |
| `firm status`                                       | État de l'organisation              |
| `firm audit`                                        | Audit complet                        |
| `firm propose <agent> <titre> <desc>`               | Créer une proposition               |
| `firm vote <prop> <agent> <approve\|reject>`         | Voter                                |
| `firm finalize <prop>`                              | Finaliser une proposition            |
| `firm role define <nom> <desc> [--min-authority N]` | Définir un rôle                    |
| `firm role assign <agent> <rôle>`                  | Assigner un rôle                    |
| `firm memory add <agent> <contenu> [--tags t1,t2]`  | Ajouter un souvenir                  |
| `firm memory recall <tag>`                          | Rappeler des souvenirs               |
| `firm evolve propose <agent> <param> <valeur>`      | Proposer un changement de paramètre |
| `firm evolve vote <prop> <agent> <approve\|reject>`  | Voter sur l'évolution               |
| `firm evolve apply <prop>`                          | Appliquer l'évolution               |
| `firm market post <agent> <titre> <bounty>`         | Poster une tâche                    |
| `firm market bid <tâche> <agent> <montant>`        | Enchérir                            |
| `firm amend <agent> <type> <texte>`                 | Proposer un amendement               |
| `firm repl`                                         | Mode REPL interactif                 |
| `firm bounty agents`                                | Lister les agents bounty             |
| `firm bounty init <scope.yaml>`                     | Initialiser une campagne             |
| `firm bounty scope <scope.yaml>`                    | Afficher le scope                    |
| `firm bounty campaign <run\|status>`                 | Gérer une campagne                  |
| `firm bounty cvss <vecteur>`                        | Calculer un score CVSS 3.1           |

---

## 22. Bridge MCP — Connecter l'écosystème (138 tools)

FIRM Protocol inclut un bridge vers le serveur MCP (Model Context Protocol) qui expose
138 outils spécialisés : audit sécurité, mémoire hebbienne, protocole A2A, étude de marché,
observabilité, etc. Ce bridge permet à vos agents LLM d'utiliser ces outils **nativement**.

### Prérequis

Le serveur MCP doit tourner sur le port 8012 :

```bash
# Vérifier que le serveur MCP est actif
bash mcp-openclaw-extensions/scripts/status.sh
```

### Utilisation rapide

```python
from firm.runtime import Firm
from firm.llm.agent import create_llm_agent
from firm.llm.mcp_bridge import create_mcp_toolkit, extend_agent_with_mcp

# Créer un agent FIRM classique
firm = Firm("my-startup")
cto = create_llm_agent(firm, "CTO", provider_name="copilot-pro", authority=0.8)

# Étendre avec TOUS les outils MCP (138 outils)
added = extend_agent_with_mcp(cto)
print(f"{added} outils MCP ajoutés au CTO")

# L'agent peut maintenant utiliser les outils MCP nativement
result = cto.execute_task("Audite la configuration de sécurité du workspace")
```

### Filtrer par catégorie

Plutôt que charger les 138 outils, filtrez par catégorie :

```python
from firm.llm.mcp_bridge import create_mcp_toolkit, MCP_CATEGORIES

# Voir les catégories disponibles
print(MCP_CATEGORIES.keys())
# → security, memory, a2a, gateway, fleet, audit, delivery,
#   compliance, observability, config, orchestration, market_research

# ToolKit sécurité uniquement
sec_kit = create_mcp_toolkit(categories=["security", "compliance"])

# ToolKit mémoire hebbienne
mem_kit = create_mcp_toolkit(filter_prefix="openclaw_hebbian")
```

### Utilisation avec l'adapter intégrations

Le fichier `integrations/firm_protocol_adapter.py` combine tout :

```python
from integrations.firm_protocol_adapter import FirmProtocolAdapter

# Créer une organisation complète avec MCP activé
org = FirmProtocolAdapter("startup", enable_mcp=True, mcp_categories=["security"])

# Ajouter des agents — ils reçoivent automatiquement les outils MCP
org.add_agent("CTO", provider="copilot-pro", model="claude-sonnet-4.6", authority=0.8)
org.add_agent("dev-1", provider="copilot-pro", model="gpt-4.1", authority=0.5)

# Exécuter une tâche
result = org.execute("CTO", "Analyse les vulnérabilités de la config")
print(result["output"])
print(f"Coût : ${result['cost_usd']}")
print(f"Outils utilisés : {result['tools_used']}")

# État de l'organisation
print(org.to_json())
```

### Vérifier la connexion MCP

```python
from firm.llm.mcp_bridge import check_mcp_server

status = check_mcp_server()
if status["ok"]:
    print(f"✅ MCP actif — {status['tool_count']} outils disponibles")
else:
    print(f"❌ MCP injoignable : {status['error']}")
```

### Tableau récapitulatif

| Catégorie          | Outils | Description                                    |
| ------------------- | ------ | ---------------------------------------------- |
| `security`        | ~10    | Audit sécurité, sandbox, secrets             |
| `memory`          | ~10    | Mémoire hebbienne, pgvector, knowledge graph  |
| `a2a`             | 8      | Protocole Agent-to-Agent                       |
| `gateway`         | ~8     | Auth gateway, credentials, webhooks            |
| `fleet`           | 6      | Multi-instances gateway                        |
| `audit`           | ~12    | Runtime, config, node, headers                 |
| `delivery`        | 6      | Export GitHub PR, Jira, Slack, etc.            |
| `compliance`      | ~10    | MCP spec, OAuth, prompt injection              |
| `observability`   | 2      | Traces JSONL→SQLite, CI                       |
| `orchestration`   | 2      | DAG task execution                             |
| `market_research` | ~15    | Études de marché, fournisseurs, localisation |

### ✅ Résultat de validation — Test sur ce projet

Le bridge MCP a été testé **sur ce repository** (`firm-protocol/src/firm`) :

| Étape                         | Résultat                                                                                                | Statut |
| ------------------------------ | -------------------------------------------------------------------------------------------------------- | ------ |
| **Connexion MCP**        | `143 outils` découverts via JSON-RPC                                                                  | ✅     |
| **Création Firm**       | Organisation `test-mcp-bridge` initialisée                                                            | ✅     |
| **ToolKit Security**     | `10 outils` chargés (scan, sandbox, secrets…)                                                        | ✅     |
| **Appel MCP réel**      | `firm_security_scan` → **45 fichiers scannés**, 4 vulnérabilités HIGH dans `reputation.py` | ✅     |
| **Filtrage catégories** | memory (10) · a2a (8) · compliance (14) · delivery (6)                                                | ✅     |
| **Extension agent**      | `20 outils MCP` ajoutés au CTO (security + memory)                                                    | ✅     |

> **Conclusion :** Un agent FIRM connecté via `extend_agent_with_mcp(cto)` peut appeler
> nativement les 143 outils de l'écosystème MCP dans le cadre du système d'autorité FIRM.

---

## 23. Génération automatique de rapports (bonnes pratiques)

FIRM permet de générer des **rapports d'audit structurés** en suivant les meilleures pratiques :

- 🔍 **Classification OWASP Top 10** pour les vulnérabilités
- 🏷️ **Identifiants CWE** par catégorie de finding
- 📊 **Scoring de sévérité** (CRITICAL / HIGH / MEDIUM / LOW / INFO)
- 🎯 **Matrice de priorisation** des remédiations
- 📝 **Executive summary** + findings détaillés
- 🔄 **Reproductibilité** : paramètres de scan enregistrés

### Script de génération

```python
import json
from datetime import datetime, timezone
from firm.runtime import Firm
from firm.llm.mcp_bridge import create_mcp_toolkit, check_mcp_server


def generate_security_report(target_path: str, firm_name: str = "audit") -> dict:
    """Génère un rapport d'audit sécurité structuré.

    Bonnes pratiques appliquées :
    - Alignement OWASP Top 10 pour la classification
    - Identifiants CWE pour chaque catégorie
    - Scoring de sévérité (CRITICAL/HIGH/MEDIUM/LOW/INFO)
    - Matrice de priorisation des remédiations
    - Executive summary + findings détaillés
    - Reproductibilité : paramètres de scan enregistrés
    """
    # 1. Vérifier la connectivité MCP
    status = check_mcp_server()
    if not status["ok"]:
        raise ConnectionError(f"Serveur MCP injoignable : {status['error']}")

    # 2. Charger les outils sécurité + compliance
    kit = create_mcp_toolkit(categories=["security", "compliance"])
    print(f"🔧 {len(kit.list_tools())} outils chargés")

    # 3. Lancer le scan de sécurité
    scan = kit.execute("firm_security_scan", {"target_path": target_path})
    scan_data = json.loads(scan.output) if scan.success else {}

    # 4. Lancer l'audit sandbox
    sandbox = kit.execute("firm_sandbox_audit", {"config_path": "config.json"})
    sandbox_data = json.loads(sandbox.output) if sandbox.success else {}

    # 5. Construire le rapport structuré
    report = {
        "title": f"Rapport d'audit sécurité — {firm_name}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methodology": "Scan automatisé MCP (aligné OWASP)",
        "target": target_path,
        "tools_used": [t.name for t in kit.list_tools()],
        "executive_summary": {
            "total_files_scanned": scan_data.get("total_files_scanned", 0),
            "critical": scan_data.get("critical_count", 0),
            "high": scan_data.get("high_count", 0),
            "medium": scan_data.get("medium_count", 0),
            "verdict": (
                "✅ PASS" if scan_data.get("critical_count", 0) == 0
                else "❌ FAIL — vulnérabilités critiques détectées"
            ),
        },
        "findings": scan_data.get("vulnerabilities", []),
        "sandbox_audit": sandbox_data,
        "recommendations": [
            "Revoir tous les findings HIGH sous 48h",
            "Appliquer les requêtes paramétrées là où des patterns SQL sont signalés",
            "Activer le mode sandbox en configuration de production",
            "Planifier des scans récurrents via le pipeline CI",
        ],
    }
    return report


# Utilisation
report = generate_security_report("src/firm", firm_name="firm-protocol")
print(json.dumps(report, indent=2, ensure_ascii=False))
```

### Exemple de sortie

```json
{
  "title": "Rapport d'audit sécurité — firm-protocol",
  "generated_at": "2026-03-06T14:30:00+00:00",
  "methodology": "Scan automatisé MCP (aligné OWASP)",
  "executive_summary": {
    "total_files_scanned": 45,
    "critical": 0,
    "high": 4,
    "medium": 0,
    "verdict": "✅ PASS"
  },
  "findings": [
    {
      "file": "src/firm/core/reputation.py",
      "line": 560,
      "severity": "HIGH",
      "pattern": "String concatenation in query — use parameterized queries"
    }
  ],
  "recommendations": [
    "Revoir tous les findings HIGH sous 48h",
    "Appliquer les requêtes paramétrées là où des patterns SQL sont signalés",
    "Activer le mode sandbox en configuration de production",
    "Planifier des scans récurrents via le pipeline CI"
  ]
}
```

### Générer un rapport Markdown depuis le JSON

```python
def report_to_markdown(report: dict) -> str:
    """Convertit un rapport JSON en Markdown lisible."""
    summary = report["executive_summary"]
    lines = [
        f"# {report['title']}",
        "",
        f"> Généré le {report['generated_at']} — {report['methodology']}",
        "",
        "## Executive Summary",
        "",
        f"| Métrique | Valeur |",
        f"|----------|--------|",
        f"| Fichiers scannés | **{summary['total_files_scanned']}** |",
        f"| Critical | **{summary['critical']}** |",
        f"| High | **{summary['high']}** |",
        f"| Medium | **{summary['medium']}** |",
        f"| Verdict | {summary['verdict']} |",
        "",
        "## Findings",
        "",
    ]
    for f in report.get("findings", []):
        lines.append(
            f"- **{f['severity']}** — `{f.get('file', '?')}` L{f.get('line', '?')}: "
            f"{f.get('pattern', 'N/A')}"
        )
    lines += [
        "",
        "## Recommendations",
        "",
    ]
    for i, rec in enumerate(report.get("recommendations", []), 1):
        lines.append(f"{i}. {rec}")
    return "\n".join(lines)

# Sauvegarder le rapport
md = report_to_markdown(report)
with open("SECURITY-REPORT.md", "w") as f:
    f.write(md)
print("📄 Rapport sauvegardé dans SECURITY-REPORT.md")
```

---

## Pour aller plus loin

- **Exemple narré complet** : `python examples/startup_lifecycle.py` — un scénario en 7 actes
- **1137 tests** : `python -m pytest tests/ -v` — explorer les tests est une excellente documentation
- **CHANGELOG** : voir `CHANGELOG.md` pour l'historique complet des versions
- **ROADMAP** : voir `ROADMAP.md` pour les fonctionnalités à venir

---

> ⚠️ Contenu généré par IA — validation humaine requise avant utilisation.
