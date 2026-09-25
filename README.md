# Бенчмарк извлечения документов на GLM 4.6

Веб-приложение для оценки качества мультимодального распознавания документов
моделью GLM 4.6: загрузка пары «эталон + скан», OCR-проход по страницам,
расчёт метрик **CER**, **WER**, **Exact Success**, времени и токенов.

## Возможности

- 3 типа документов: `text_only`, `text_tables`, `text_tables_images` —
  набор учитываемых сущностей (текст / таблицы / изображения) зависит от типа.
- Загрузка пары файлов (PDF/DOCX): эталон с текстовым слоем и скан без него
  (проверка текстового слоя на сервере).
- Распознавание страниц: рендер в изображения → multimodal GLM →
  распознанный JSON (текст / таблицы / кропы изображений с bbox).
- Метрики: CER, WER, Exact Success (после нормализации), постраничный разбор,
  метрики таблиц, время запроса и токены (prompt/completion/cached/reasoning).
- Diff-вьюер текста, превью эталона и результата, история сессий с
  восстановлением и удалением.
- Без ключа API работает **mock-режим** (заглушка) — удобно для smoke-тестов UI.

## Стек

| Слой    | Технологии                                                                 |
| ------- | -------------------------------------------------------------------------- |
| Backend | Python 3.11+, FastAPI, Pydantic v2, pymupdf, python-docx, pytest            |
| Frontend| React 18, TypeScript 5, Vite 5, Zustand, Tailwind 3                         |
| API     | GLM 4.6 через OpenAI-совместимый endpoint (Z.AI / BigModel)                |

## Структура проекта

```
OCR_web_test/
├── .env.example          # шаблон окружения (скопировать в .env)
├── requirements.txt      # зависимости backend
├── data/                 # загрузки, рендеры страниц, JSON сессий (git-ignored)
├── backend/
│   ├── app/
│   │   ├── main.py       # приложение, CORS, раздача собранного SPA
│   │   ├── config.py     # Settings (pydantic-settings, читает .env)
│   │   ├── api/routes.py # /api/*
│   │   ├── schemas/      # Pydantic-модели (document, recognition, metrics…)
│   │   └── services/     # glm_client, glm_mock, parsers, pdf_parser,
│   │                     # metrics, normalization, storage, images
│   └── tests/            # pytest (API, метрики, парсеры, нормализация…)
└── frontend/
    ├── src/
    │   ├── App.tsx                 # шаги: тип → файлы → распознавание → метрики
    │   ├── store/useBenchmarkStore.ts
    │   ├── api/client.ts           # /api/upload, /recognize, /metrics, /results
    │   └── components/             # Stepper, Dropzone, RecognizePanel,
    │                               # MetricsPanel, DiffViewer, DocumentPreview…
    └── package.json
```

## Быстрый старт

### 1. Backend

```bat
python -m venv .venv
.venv\Scripts\activate          :: macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          :: macOS/Linux: cp .env.example .env
python -m uvicorn app.main:app --app-dir backend --port 8000
```

### 2. Frontend (dev)

```bat
cd frontend
npm install
npm run dev                     # http://localhost:5173, проксирует /api на :8000
```

### 3. Продакшен-сборка

```bat
cd frontend
npm run build                   # кладёт dist/
python -m uvicorn app.main:app --app-dir backend --port 8000
```

FastAPI отдаёт собранный SPA и API с одного порта.

## Ключ GLM 4.6

API-ключ задается **только через окружение** (`.env` или переменные окружения);
в коде он никогда не хардкодится.

1. Зарегистрируйтесь: [Z.AI](https://z.ai) (international) или
   [BigModel](https://open.bigmodel.cn) (КНР) → раздел API Keys.
2. В `.env` укажите `GLM_API_KEY=...` (принимаются также `ZAI_API_KEY` и
   `ZHIPUAI_API_KEY`) и при необходимости `GLM_BASE_URL` вашей платформы.
3. Важно: страницы отправляются как **изображения**, поэтому нужна
   multimodal-модель: `GLM_MODEL=glm-4.6v` (обычный `glm-4.6` — text-only!).
   Цепочка: `GLM_MODEL` → `GLM_MODEL_FALLBACKS` (используется первый
   endpoint'ом принятый вариант).
4. Без ключа (или при `GLM_MOCK=true`) работает mock-клиент — метрики и UI
   доступны, но для настоящего бенчмарка `GLM_MOCK` должен быть `false`.

Ключевые переменные (полный список — в `.env.example`):

| Переменная             | Назначение                              | По умолчанию                    |
| ---------------------- | --------------------------------------- | ------------------------------- |
| `GLM_API_KEY`          | ключ API                                | пусто (mock)                    |
| `GLM_BASE_URL`         | OpenAI-совместимый endpoint             | `https://api.z.ai/api/paas/v4/` |
| `GLM_MODEL`            | vision-модель                           | `glm-4.6v`                      |
| `GLM_MOCK`             | офлайн-режим                            | `false`                         |
| `MAX_UPLOAD_MB`        | лимит размера загрузки                  | `50`                            |
| `RENDER_DPI`           | DPI рендеринга страниц скана            | `200`                           |
| `TEXT_LAYER_MIN_CHARS` | минимум символов «текстового слоя»      | `20`                            |
| `DATA_DIR`             | хранилище сессий                        | `./data`                        |
| `CORS_ORIGINS`         | разрешённые источники (dev: :5173)      | `http://localhost:5173,…`       |

## API

| Метод  | Путь                       | Назначение                                 |
| ------ | -------------------------- | ------------------------------------------ |
| GET    | `/api/health`              | статус, модель, режим, лимиты              |
| GET    | `/api/document-types`      | справочник типов документов                |
| POST   | `/api/upload`              | загрузка пары (multipart), создание сессии |
| POST   | `/api/recognize`           | OCR-проход по страницам (JSON body)        |
| POST   | `/api/metrics`             | расчёт отчёта (нормализация, diff)         |
| GET    | `/api/results/{session_id}`| полный результат сессии                    |
| GET    | `/api/sessions`            | история сессий                             |
| DELETE | `/api/results/{session_id}`| удаление сессии                            |

## Метрики

- **CER** = Levenshtein(символы) / длина эталона; **WER** — по словам.
- **Exact Success** — «эталон == результат» после нормализации (регистр,
  пробелы, кавычки, тире; опционально пунктуация и диакритика).
- Нормализация переключается в UI; изменение настроек инвалидирует кнопку до
  повторного расчёта. «Рассчитать метрики» активна только когда готовы
  **оба** JSON: эталонный и распознанный.
- Время и токены берутся из метаданных запросов к GLM (включая повторы и
  fallback-модели).

Формат JSON документа:
`{document_type, source, session_id, pages: [{page_number, width, height, blocks: [...]}], …}`.
Блоки: `text` (content), `table` (rows), `image` (url кропа, caption, bbox).

## Тесты

```bat
.venv\Scripts\activate
python -m pytest backend/tests -q
```

Фронтенд: `cd frontend && npm run typecheck && npm run build`.

## Примечания

- Эталон и результат хранятся раздельными JSON; кропы изображений никогда не
  распознаются как текст.
- `.env`, `data/`, `node_modules/`, `frontend/dist/` — в `.gitignore`;
  секреты не коммитятся.

