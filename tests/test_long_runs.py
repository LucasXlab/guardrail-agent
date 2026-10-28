from guardrail_agent import AuditChain, simulate


def test_long_synthetic_run_has_valid_complete_chain():
    portfolio, audit, rejected, config = simulate(1000, 3, "chaotic")
    assert len(audit.records) > 1000
    assert len(portfolio.equity_history) == 1000
    assert portfolio.cash >= 0
    assert audit.verify() is None


def test_full_verification_still_detects_old_record_mutation_after_append():
    chain = AuditChain()
    for index in range(5):
        chain.add({"index": index})
    chain.records[1]["payload"]["index"] = 999
    chain.add({"index": 5})
    assert chain.verify() == 1
