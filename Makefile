# ============================================================
#  YouTube Shorts Telegram Bot — Makefile
# ============================================================

IMAGE_NAME   := youtube-shorts-bot
CONTAINER    := youtube-shorts-bot
PYTHON_FILES := main.py bot.py download_queue.py config.py logger.py

.DEFAULT_GOAL := help

# ── Colours ─────────────────────────────────────────────────
BOLD  := \033[1m
RESET := \033[0m
CYAN  := \033[36m
GREEN := \033[32m
YELLOW:= \033[33m

# ── Help ────────────────────────────────────────────────────
.PHONY: help
help:
	@printf "$(BOLD)YouTube Shorts Bot$(RESET)\n\n"
	@printf "$(CYAN)Local development$(RESET)\n"
	@printf "  $(BOLD)make install$(RESET)        Install production dependencies via uv\n"
	@printf "  $(BOLD)make install-dev$(RESET)    Install all dependencies including dev tools\n"
	@printf "  $(BOLD)make run$(RESET)            Run the bot locally\n"
	@printf "\n$(CYAN)Code quality$(RESET)\n"
	@printf "  $(BOLD)make lint$(RESET)           Run ruff linter\n"
	@printf "  $(BOLD)make lint-fix$(RESET)       Run ruff linter with auto-fix\n"
	@printf "  $(BOLD)make format$(RESET)         Run ruff formatter\n"
	@printf "  $(BOLD)make type-check$(RESET)     Run mypy type checker\n"
	@printf "  $(BOLD)make check$(RESET)          Run lint + type-check (CI gate)\n"
	@printf "  $(BOLD)make syntax-check$(RESET)   Verify Python syntax compiles cleanly\n"
	@printf "\n$(CYAN)Docker (standalone)$(RESET)\n"
	@printf "  $(BOLD)make docker-build$(RESET)   Build the Docker image\n"
	@printf "  $(BOLD)make docker-run$(RESET)     Run container in the background\n"
	@printf "  $(BOLD)make docker-stop$(RESET)    Stop the running container\n"
	@printf "  $(BOLD)make docker-restart$(RESET) Restart the running container\n"
	@printf "  $(BOLD)make docker-logs$(RESET)    Tail container logs\n"
	@printf "  $(BOLD)make docker-shell$(RESET)   Open a shell inside the container\n"
	@printf "  $(BOLD)make docker-clean$(RESET)   Remove container and image\n"
	@printf "\n$(CYAN)Docker Compose$(RESET)\n"
	@printf "  $(BOLD)make up$(RESET)             Build and start via docker-compose (detached)\n"
	@printf "  $(BOLD)make down$(RESET)           Stop and remove compose services\n"
	@printf "  $(BOLD)make compose-logs$(RESET)   Tail compose service logs\n"
	@printf "  $(BOLD)make compose-restart$(RESET) Restart compose services\n"
	@printf "\n$(CYAN)Housekeeping$(RESET)\n"
	@printf "  $(BOLD)make clean$(RESET)          Remove downloads, caches and build artefacts\n"
	@printf "  $(BOLD)make clean-downloads$(RESET) Remove only the downloads directory\n"

# ── Local development ────────────────────────────────────────
.PHONY: install
install:
	@printf "$(GREEN)Installing production dependencies...$(RESET)\n"
	uv sync

.PHONY: install-dev
install-dev:
	@printf "$(GREEN)Installing all dependencies (incl. dev tools)...$(RESET)\n"
	uv sync --all-extras

.PHONY: run
run:
	@printf "$(GREEN)Starting bot...$(RESET)\n"
	uv run python main.py

# ── Code quality ─────────────────────────────────────────────
.PHONY: lint
lint:
	@printf "$(CYAN)Running ruff linter...$(RESET)\n"
	uv run ruff check .

.PHONY: lint-fix
lint-fix:
	@printf "$(CYAN)Running ruff linter with auto-fix...$(RESET)\n"
	uv run ruff check . --fix

.PHONY: format
format:
	@printf "$(CYAN)Running ruff formatter...$(RESET)\n"
	uv run ruff format .

.PHONY: type-check
type-check:
	@printf "$(CYAN)Running mypy type checker...$(RESET)\n"
	uv run mypy .

.PHONY: syntax-check
syntax-check:
	@printf "$(CYAN)Checking Python syntax...$(RESET)\n"
	uv run python -m py_compile $(PYTHON_FILES)
	@printf "$(GREEN)All files compile cleanly.$(RESET)\n"

.PHONY: check
check: lint type-check
	@printf "$(GREEN)All checks passed.$(RESET)\n"

# ── Docker (standalone) ──────────────────────────────────────
.PHONY: docker-build
docker-build:
	@printf "$(GREEN)Building Docker image '$(IMAGE_NAME)'...$(RESET)\n"
	docker build -t $(IMAGE_NAME) .

.PHONY: docker-run
docker-run:
	@printf "$(GREEN)Starting container '$(CONTAINER)'...$(RESET)\n"
	docker run -d \
		--name $(CONTAINER) \
		--restart unless-stopped \
		--env-file .env \
		-v "$$(pwd)/downloads:/app/downloads" \
		$(IMAGE_NAME)
	@printf "$(GREEN)Container started. Use 'make docker-logs' to follow logs.$(RESET)\n"

.PHONY: docker-stop
docker-stop:
	@printf "$(YELLOW)Stopping container '$(CONTAINER)'...$(RESET)\n"
	docker stop $(CONTAINER) || true
	docker rm $(CONTAINER)   || true

.PHONY: docker-restart
docker-restart: docker-stop docker-run

.PHONY: docker-logs
docker-logs:
	docker logs -f $(CONTAINER)

.PHONY: docker-shell
docker-shell:
	docker exec -it $(CONTAINER) /bin/bash

.PHONY: docker-clean
docker-clean: docker-stop
	@printf "$(YELLOW)Removing image '$(IMAGE_NAME)'...$(RESET)\n"
	docker rmi $(IMAGE_NAME) || true

# ── Docker Compose ───────────────────────────────────────────
.PHONY: up
up:
	@printf "$(GREEN)Starting services via docker-compose...$(RESET)\n"
	docker compose up --build -d
	@printf "$(GREEN)Services started. Use 'make compose-logs' to follow logs.$(RESET)\n"

.PHONY: down
down:
	@printf "$(YELLOW)Stopping compose services...$(RESET)\n"
	docker compose down

.PHONY: compose-logs
compose-logs:
	docker compose logs -f

.PHONY: compose-restart
compose-restart:
	docker compose restart

# ── Housekeeping ─────────────────────────────────────────────
.PHONY: clean-downloads
clean-downloads:
	@printf "$(YELLOW)Removing downloads directory contents...$(RESET)\n"
	rm -rf downloads/*

.PHONY: clean
clean: clean-downloads
	@printf "$(YELLOW)Removing caches and build artefacts...$(RESET)\n"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@printf "$(GREEN)Clean complete.$(RESET)\n"
