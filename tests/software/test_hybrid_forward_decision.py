from pathlib import Path
import importlib.util
import json

import numpy as np
import pytest

pd = pytest.importorskip('pandas', reason='Requires the research runtime')


script = Path(__file__).resolve().parents[2] / 'scripts/hybrid_forward_decision.py'
spec = importlib.util.spec_from_file_location('forward_decision_tested', script)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.skipif(not (runner.BASELINE / 'candidate_information_prices.csv').exists(), reason='Requires the local frozen Phase 1 research artifacts')
def test_frozen_native_fit_and_epoch_reuse(tmp_path):
    # Real historical prices for the first mature baseline fit; never an evaluation receipt.
    prices = pd.read_csv(runner.BASELINE / 'candidate_information_prices.csv', index_col='date', parse_dates=True).iloc[:335].copy()
    prices.loc[:, list(runner.EQUITY_IDS)] *= 1000
    dates = [str(i.date()) for i in prices.index]

    def evaluate(i, offset, state, block=None):
        table = prices.iloc[:i+1]
        panel = dict(assets=list(table.columns), sessions=dates[:i+1], information=table, provenance={'test': 'historical'})
        if block:
            panel['decision_block'] = block
        return runner.decision(panel, dates[i], offset, tmp_path, state)

    first = evaluate(319, 0, {})
    assert first['status'] == 'TARGET' and first['regime'] == 'normal'
    assert first['shares']['growth'] == {'candidate': .60, 'regime_only': .60, 'v1': .75, 'bl_ml': 0.}
    assert first['weights']['growth']['candidate'] == first['weights']['growth']['regime_only']
    np.testing.assert_allclose(first['weights']['growth']['candidate'],
                               .8*np.array(first['weights']['growth']['v1']) + .2*np.array(first['weights']['growth']['bl_ml']))
    model = first['state']['model']
    manifest = json.loads((tmp_path / model['file']).read_text())
    assert manifest['fit_epoch'] == dates[319] and manifest['training_cutoff'] == dates[313]
    assert list(manifest['asset_ids']) == first['state']['selection']['selected_equity_ids']
    for asset in manifest['asset_ids']:
        a = manifest['by_asset'][asset]
        assert a['train_label_end'] < a['validation_start']
        assert a['validation_label_end'] == dates[313]
        assert [m['seed'] for m in a['members']] == [42, 43, 44, 45, 46]
    assert all(len(w) == 32 and np.isclose(sum(w), 1) for variants in first['weights'].values() for w in variants.values())
    runner.verify_state(tmp_path, first['state'])
    # Compare the native serialization and best_iteration against the original frozen sklearn fit.
    reference = runner.frozen()[0](model_params={'n_jobs': 1})
    selected = manifest['asset_ids']
    reference.train(prices[selected].iloc[:314] / 1000, verbose=False)
    reference.predict(prices[selected].iloc[:319] / 1000)
    for row in reference.prediction_audit:
        evidence = first['predictions'][row['asset']]
        np.testing.assert_array_equal(evidence['members'], row['member_predictions'])
        assert (evidence['forecast'], evidence['confidence']) == (row['prediction_mean'], row['confidence'])
    block = {'reason': 'VFF_STALE', 'details': {'age_days': 11}}
    held = evaluate(319, 0, {}, block)
    assert held['reason'] == 'VFF_STALE' and held['status'] == 'HOLD' and 'weights' not in held
    assert held['details'] == block['details'] and held['state'] == first['state']
    second = evaluate(324, 5, held['state'])
    assert second['state'] == first['state']
    if second['status'] == 'TARGET':
        assert second['feature_end'] == dates[323]
    third = evaluate(329, 10, second['state'])
    assert third['state']['model'] != model
    assert third['state']['selection'] == first['state']['selection']
    assert evaluate(334, 15, second['state'])['reason'] == 'MISSING_SCHEDULED_MODEL'
    directory = (tmp_path / model['file']).parent
    booster = directory / manifest['by_asset'][manifest['asset_ids'][0]]['members'][0]['file']
    booster.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash'):
        runner.verify_state(tmp_path, first['state'])
    with pytest.raises(ValueError, match='hash'):
        evaluate(324, 5, first['state'])
