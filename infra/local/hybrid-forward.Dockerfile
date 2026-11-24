FROM portfolio-software-ml:local AS dependencies
USER root
RUN python -m pip install --no-cache-dir pandas==2.2.3 scipy==1.17.1 scikit-learn==1.8.0 matplotlib==3.10.8 joblib==1.5.3

FROM dependencies
WORKDIR /study
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/mpl HOME=/tmp
ENV PYTHONPATH=/study:/study/services/quant-serving/src:/study/packages/contracts/src:/study/packages/portfolio-core/src:/study/services/market-data/src:/study/scripts
COPY packages/contracts/src packages/contracts/src
COPY packages/portfolio-core/src packages/portfolio-core/src
COPY services/market-data/src services/market-data/src
COPY services/quant-serving/src services/quant-serving/src
COPY outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110 outputs/step1/readiness_20261012/runs/availability-observed-contract-20261012T233110
COPY scripts/hybrid_forward_*.py scripts/eval_hybrid_policy.py scripts/
USER service
ENTRYPOINT ["python", "scripts/hybrid_forward_study.py"]
