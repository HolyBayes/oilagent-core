# Два независимых Git-репозитория

Согласованная структура workspace:

```text
OilAgent/
  core/.git/            # история кода разработчиков
  core/src/             # core и два MCP adapters
  core/tests/           # доверенные проверки
  core/docs/            # спецификация, результаты, исходное задание
  core/.env             # ignored secrets
  core/workspace/       # ignored runtime statuses/logs
  evolution/.git/       # отдельная история локальных самоулучшений
  evolution/policies/
  evolution/ouroboros_skills/
  workspace/upstream/   # внешний pinned Ouroboros, не часть двух репозиториев
```

Core и evolution — отдельные repository roots, не submodules и не worktrees одного Git. Родительский OilAgent workspace не имеет `.git`. История evolution перенесена из успешного smoke-прогона без переписывания seed и candidate commits; прежние SHA доступны в сохранённых ветках `candidate/<id>`. Последующие smoke используют временные Git, не канонический evolution.

`EVOLUTION_REPO_PATH=../evolution` задаёт canonical repository; `WORKSPACE_PATH=workspace/runtime` задаёт невeрсионируемое состояние сервиса. Относительные пути разрешаются от core, независимо от текущей shell directory. Git внутри runtime workspace допустим только для изолированных тестовых прогонов. Source instruction skill находится в evolution, trusted backend и schema — в core.

Из корня workspace:

```bash
git -C core status --short
git -C core log --oneline -3
git -C evolution status --short
git -C evolution log --all --oneline --decorate -5
```

Секреты и runtime artifacts не включаются в коммиты. Исходный DOCX и первоначальный архитектурный набросок включены в core/docs для происхождения требований. Готовность контейнеров, review и выпуска по-прежнему отражается в INTEGRATION_STATUS.md.

Раздельные Git-истории обеспечивают раздельное версионирование, но не OS-изоляцию. Удалённые remotes не настроены и публикации не было. Локальные коммиты не означают human-approved production release. Git hooks/branch protection и доверенный release manifest требуют последующей реализации.
