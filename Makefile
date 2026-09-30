# bnbot — canonical entry points
.PHONY: test backtest paper status report fetch

test:            ## run the full unittest suite (58 tests)
	python -m unittest discover -s tests -v

fetch:           ## incrementally refresh market data via proxy
	python -m bnbot.data --fetch --proxy http://127.0.0.1:7890

backtest:        ## walk-forward backtest (IS/OOS split)
	python -m bnbot.backtest --walk-forward

paper:           ## one paper round
	python -m bnbot.live --paper --once --proxy http://127.0.0.1:7890

status:          ## read-only status server on :8787
	python -m bnbot.server --port 8787

report:          ## real-money readiness gates (machine-checkable)
	python -m bnbot.report
