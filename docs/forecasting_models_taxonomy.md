# Forecasting Models — Comprehensive Taxonomy

> Scope: statistical, econometric, financial, machine-learning, deep-learning, probabilistic, and hybrid forecasting models.  
> Emphasis: ARIMA-family and related time-series models.

---

## 1. Baseline / Naive Forecasts

- Naive forecast
- Last-value forecast
- Seasonal naive
- Mean forecast
- Median forecast
- Drift forecast
- Random-walk forecast
- Random walk with drift
- Historical-average forecast
- Moving-average forecast
- Weighted moving average
- Rolling-window forecast
- Expanding-window forecast

---

## 2. Moving-Average and Smoothing Models

### 2.1 Moving-Average Filters

- Simple Moving Average (SMA)
- Weighted Moving Average (WMA)
- Exponentially Weighted Moving Average (EWMA)
- Exponential Moving Average (EMA)
- Double Moving Average
- Triangular Moving Average
- Hull Moving Average
- Adaptive Moving Average
- Kaufman Adaptive Moving Average (KAMA)

### 2.2 Exponential Smoothing

- Simple Exponential Smoothing (SES)
- Brown's Simple Exponential Smoothing
- Double Exponential Smoothing
- Holt Linear Trend
- Holt Damped Trend
- Holt-Winters Additive
- Holt-Winters Multiplicative
- Seasonal Exponential Smoothing
- Damped Seasonal Exponential Smoothing
- Multiple-Seasonal Exponential Smoothing
- ETS models
  - ETS(A,N,N)
  - ETS(M,N,N)
  - ETS(A,A,N)
  - ETS(A,Ad,N)
  - ETS(M,A,N)
  - ETS(M,Ad,N)
  - ETS(A,A,A)
  - ETS(A,A,M)
  - ETS(M,A,A)
  - ETS(M,A,M)
  - analogous damped-trend variants

### 2.3 Complex Exponential-Smoothing Extensions

- BATS
- TBATS
- Dynamic Harmonic Regression with ETS errors
- Theta Method
- Optimized Theta Method
- Dynamic Optimized Theta
- Multiple Theta Method
- Croston's Method
- Croston-SBA
- Croston-TSB
- ADIDA
- IMAPA
- SES with intermittent-demand adjustments

---

# 3. AR / MA / ARMA Family

## 3.1 Autoregressive Models

- AR
- AR(p)
- Autoregression with deterministic trend
- Autoregression with seasonal terms
- Autoregression with exogenous variables
- Distributed-lag autoregression
- Dynamic autoregression
- Regularized autoregression
- Sparse autoregression
- Bayesian autoregression

General form:

\[
y_t = c + \sum_{i=1}^{p}\phi_i y_{t-i} + \varepsilon_t
\]

## 3.2 Moving-Average Models

- MA
- MA(q)
- Seasonal MA
- MA with exogenous covariates

\[
y_t = \mu + \varepsilon_t + \sum_{j=1}^{q}\theta_j\varepsilon_{t-j}
\]

## 3.3 ARMA

- ARMA(p,q)
- Seasonal ARMA
- ARMA with deterministic trend
- ARMA with interventions
- ARMA with exogenous regressors
- Bayesian ARMA
- Fractional ARMA variants

---

# 4. ARIMA Family

## 4.1 ARIMA

- ARIMA(p,d,q)
- Box-Jenkins ARIMA
- ARIMA with drift
- ARIMA with trend
- ARIMA with intervention variables
- ARIMA with calendar effects
- ARIMA with structural-break dummies

\[
\Phi(B)(1-B)^d y_t
=
c+\Theta(B)\varepsilon_t
\]

## 4.2 Seasonal ARIMA

- SARIMA
- SARIMA(p,d,q)(P,D,Q)\(_s\)
- Seasonal ARIMA with drift
- Multiplicative seasonal ARIMA

\[
\Phi(B)\Phi_s(B^s)(1-B)^d(1-B^s)^D y_t
=
\Theta(B)\Theta_s(B^s)\varepsilon_t
\]

## 4.3 ARIMAX / SARIMAX

- ARIMAX
- Dynamic Regression with ARIMA errors
- SARIMAX
- Regression with SARIMA errors
- Transfer-function ARIMA
- Intervention ARIMA
- Distributed-lag ARIMAX

## 4.4 Fractional Integration

- ARFIMA
- FARIMA
- Fractionally Integrated ARMA
- Seasonal ARFIMA
- Gegenbauer ARMA
- Gegenbauer ARFIMA
- Long-memory ARIMA
- FIGARCH-related mean models

## 4.5 Other ARIMA Extensions

- Vector ARIMA
- VARIMA
- Structural ARIMA
- Bayesian ARIMA
- Robust ARIMA
- Threshold ARIMA
- Regime-switching ARIMA
- Time-varying-parameter ARIMA
- Functional ARIMA
- Spatial ARIMA
- Spatio-temporal ARIMA
- ARIMA-GARCH
- ARIMA-EGARCH
- ARIMA-GJR-GARCH
- ARIMA-SVR
- ARIMA-ANN
- ARIMA-LSTM
- ARIMA-XGBoost
- wavelet-ARIMA
- EMD-ARIMA

---

# 5. Integrated and Cointegration Models

- I(0) models
- I(1) models
- I(d) models
- Fractionally integrated I(d) models
- Error Correction Model (ECM)
- Vector Error Correction Model (VECM)
- Engle-Granger ECM
- Johansen VECM
- Autoregressive Distributed Lag (ARDL)
- Bounds-testing ARDL
- Nonlinear ARDL (NARDL)
- Panel ARDL
- Dynamic OLS
- Fully Modified OLS
- Cointegrated VAR
- Cointegrated state-space model

---

# 6. Multivariate Autoregressive Models

## 6.1 VAR Family

- VAR
- VAR(p)
- Structural VAR (SVAR)
- Bayesian VAR (BVAR)
- Sparse VAR
- Regularized VAR
- LASSO VAR
- Ridge VAR
- Elastic-Net VAR
- Factor-Augmented VAR (FAVAR)
- Global VAR (GVAR)
- Panel VAR
- Time-Varying Parameter VAR (TVP-VAR)
- Markov-Switching VAR
- Threshold VAR
- Smooth-Transition VAR
- Quantile VAR
- Functional VAR
- Spatial VAR
- Mixed-Frequency VAR
- MIDAS-VAR
- VAR with stochastic volatility
- BVAR with stochastic volatility
- VARMA
- VARIMA
- VARMAX
- Bayesian VARMA

## 6.2 Dynamic Factor Models

- Dynamic Factor Model (DFM)
- Static Factor Model
- Approximate Factor Model
- Factor-Augmented Regression
- Factor-Augmented VAR
- Generalized Dynamic Factor Model
- Dynamic Principal Components
- State-space dynamic factor model
- Mixed-frequency dynamic factor model

---

# 7. State-Space Models

- Linear State-Space Model
- Gaussian State-Space Model
- Dynamic Linear Model (DLM)
- Structural Time Series Model
- Unobserved Components Model (UCM)
- Local Level Model
- Local Linear Trend Model
- Local Quadratic Trend Model
- Seasonal State-Space Model
- Cyclical State-Space Model
- Regression State-Space Model
- Time-Varying Parameter Model
- Dynamic Regression Model
- Dynamic Generalized Linear Model
- Dynamic Bayesian Model
- Bayesian Structural Time Series (BSTS)
- Dynamic Factor State-Space Model
- Multivariate State-Space Model
- Non-Gaussian State-Space Model
- Nonlinear State-Space Model
- Switching State-Space Model
- Hidden Markov State-Space Model
- Stochastic-volatility state-space model

### Filtering / Estimation Methods

- Kalman Filter
- Extended Kalman Filter
- Unscented Kalman Filter
- Ensemble Kalman Filter
- Particle Filter
- Bootstrap Particle Filter
- Auxiliary Particle Filter
- Rao-Blackwellized Particle Filter
- Kalman Smoother
- Rauch-Tung-Striebel Smoother
- Particle Smoother

---

# 8. Structural / Decomposition Models

- Classical Additive Decomposition
- Classical Multiplicative Decomposition
- STL
- MSTL
- X-11
- X-12-ARIMA
- X-13ARIMA-SEATS
- SEATS
- TRAMO/SEATS
- Structural Time Series
- Basic Structural Model
- Unobserved Components Model
- Trend-Cycle Decomposition
- Hodrick-Prescott Filter
- Baxter-King Filter
- Christiano-Fitzgerald Filter
- Beveridge-Nelson Decomposition
- Seasonal-Trend decomposition using LOESS
- Fourier decomposition
- Harmonic regression
- Dynamic harmonic regression
- Wavelet decomposition
- Empirical Mode Decomposition (EMD)
- Ensemble EMD
- Complete Ensemble EMD
- Variational Mode Decomposition (VMD)
- Singular Spectrum Analysis (SSA)
- Multichannel SSA
- Caterpillar SSA

---

# 9. Regression-Based Forecasting

- Ordinary Least Squares
- Generalized Least Squares
- Weighted Least Squares
- Robust Regression
- Ridge Regression
- LASSO
- Elastic Net
- Adaptive LASSO
- Group LASSO
- Sparse Group LASSO
- Principal Component Regression
- Partial Least Squares
- Polynomial Regression
- Spline Regression
- Regression Splines
- Natural Splines
- Smoothing Splines
- Generalized Additive Models (GAM)
- Generalized Linear Models (GLM)
- Generalized Additive Models for Location, Scale and Shape
- Quantile Regression
- Bayesian Linear Regression
- Bayesian Dynamic Regression
- Time-Varying Coefficient Regression
- Distributed Lag Models
- Almon Distributed Lag
- Koyck Lag Model
- Dynamic Regression
- Transfer Function Model

---

# 10. Mixed-Frequency Forecasting

- MIDAS Regression
- U-MIDAS
- Restricted MIDAS
- Almon-lag MIDAS
- Exponential Almon MIDAS
- MIDAS-AR
- MIDAS-ADL
- MIDAS-VAR
- Mixed-Frequency VAR
- Mixed-Frequency Bayesian VAR
- Mixed-Frequency Dynamic Factor Model
- Bridge Equations
- State-space mixed-frequency models

---

# 11. Volatility Models

## 11.1 ARCH Family

- ARCH
- GARCH
- GARCH(p,q)
- IGARCH
- EGARCH
- GJR-GARCH
- TGARCH
- TARCH
- APARCH
- PARCH
- NGARCH
- NAGARCH
- QGARCH
- AVGARCH
- HYGARCH
- FIGARCH
- FIEGARCH
- FIAPARCH
- Component GARCH
- CGARCH
- Multiplicative Component GARCH
- Realized GARCH
- HEAVY model
- GARCH-M
- EGARCH-M
- Stochastic GARCH
- Bayesian GARCH

## 11.2 Multivariate GARCH

- VECH
- Diagonal VECH
- BEKK-GARCH
- Diagonal BEKK
- CCC-GARCH
- DCC-GARCH
- ADCC-GARCH
- GO-GARCH
- Factor GARCH
- Orthogonal GARCH
- Copula-GARCH
- Dynamic Copula GARCH

## 11.3 Realized-Volatility Models

- HAR
- HAR-RV
- HARQ
- HAR-CJ
- HAR with jumps
- Realized GARCH
- Realized stochastic volatility
- Realized kernel models
- Multipower variation models

---

# 12. Stochastic Volatility Models

- Stochastic Volatility (SV)
- Lognormal SV
- SV with leverage
- SV with jumps
- SV with Student-t errors
- Multivariate SV
- Factor SV
- Long-memory SV
- Fractional SV
- Rough Volatility
- Rough Bergomi
- Heston stochastic-volatility model
- SABR
- 3/2 volatility model
- Bates model
- Hull-White stochastic volatility
- Wishart stochastic volatility

---

# 13. Regime-Switching and Hidden-State Models

- Markov Switching Model
- Markov-Switching AR
- Markov-Switching ARMA
- Markov-Switching ARIMA
- Markov-Switching VAR
- Markov-Switching GARCH
- Markov-Switching Dynamic Regression
- Hamilton Regime-Switching Model
- Hidden Markov Model (HMM)
- Hidden Semi-Markov Model
- Switching State-Space Model
- Switching Kalman Filter
- Threshold Autoregression (TAR)
- Self-Exciting TAR (SETAR)
- Open-Loop TAR
- Smooth Transition Autoregression (STAR)
- Logistic STAR (LSTAR)
- Exponential STAR (ESTAR)
- Smooth Transition Regression
- Threshold VAR
- Smooth Transition VAR
- Change-Point Models
- Bayesian Change-Point Models

---

# 14. Nonlinear Classical Time-Series Models

- Nonlinear AR
- Nonlinear ARMA
- NAR
- NARX
- NARMAX
- Bilinear Time-Series Model
- Exponential Autoregressive Model
- Threshold Autoregression
- Smooth Transition Autoregression
- Neural Autoregression
- Kernel Autoregression
- Additive Autoregression
- Functional-Coefficient Autoregression
- State-Dependent Autoregression
- Chaos-based forecasting
- Local Linear Forecasting
- Nearest-Neighbor Time-Series Forecasting
- Analog forecasting
- Delay-coordinate embedding models

---

# 15. Long-Memory Models

- ARFIMA
- FARIMA
- Fractional Gaussian Noise models
- Fractional Brownian Motion
- FIGARCH
- FIEGARCH
- FIAPARCH
- HYGARCH
- Long-memory stochastic volatility
- Gegenbauer processes
- Seasonal long-memory models
- Multifractal models
- Multifractal Random Walk
- MSM — Markov-Switching Multifractal

---

# 16. Count / Discrete Time-Series Models

- Poisson Autoregression
- Poisson INGARCH
- Negative Binomial INGARCH
- Integer-Valued AR (INAR)
- INAR(1)
- INARMA
- Integer-Valued GARCH
- Zero-Inflated Count Time Series
- Hurdle Time-Series Models
- Dynamic Poisson Models
- Dynamic Negative Binomial Models
- State-space count models

---

# 17. Duration, Intensity, and Point-Process Forecasting

- Autoregressive Conditional Duration (ACD)
- Log-ACD
- Weibull ACD
- Burr ACD
- Hawkes Process
- Multivariate Hawkes Process
- Self-Exciting Point Process
- Self-Correcting Point Process
- Cox Process
- Doubly Stochastic Poisson Process
- Marked Point Process
- Neural Hawkes Process
- Temporal Point Process
- Renewal Process Models

---

# 18. Survival / Hazard Forecasting

- Kaplan-Meier
- Cox Proportional Hazards
- Accelerated Failure Time Models
- Parametric Survival Models
- Weibull Survival Model
- Exponential Survival Model
- Gompertz Model
- Log-Logistic Survival Model
- Competing Risks
- Recurrent Event Models
- Dynamic Survival Models
- Random Survival Forests
- DeepSurv
- DeepHit

---

# 19. Machine-Learning Forecasting

## 19.1 Trees

- Decision Tree Regression
- Regression Trees
- Model Trees
- M5 Model Tree

## 19.2 Randomized / Ensemble Trees

- Random Forest
- Extra Trees
- Random Forest Quantile Regression
- Random Survival Forest

## 19.3 Boosting

- Gradient Boosting Machine
- XGBoost
- LightGBM
- CatBoost
- AdaBoost Regression
- HistGradientBoosting
- Quantile Gradient Boosting
- NGBoost

## 19.4 Support Vector Methods

- Support Vector Regression (SVR)
- ε-SVR
- ν-SVR
- Kernel SVR
- Least-Squares SVM
- Relevance Vector Machine

## 19.5 Nearest-Neighbor Methods

- k-Nearest Neighbors Regression
- Distance-weighted kNN
- Analog Forecasting
- Local Nearest-Neighbor Forecasting

## 19.6 Kernel Methods

- Kernel Ridge Regression
- Gaussian Process Regression
- Kernel Regression
- Nadaraya-Watson Regression
- Local Polynomial Regression

---

# 20. Gaussian-Process Forecasting

- Gaussian Process Regression
- Gaussian Process Time Series
- Sparse Gaussian Processes
- Variational Gaussian Processes
- Deep Gaussian Processes
- Multi-Output Gaussian Processes
- Coregionalized Gaussian Processes
- Spectral Mixture Gaussian Processes
- Periodic Gaussian Processes
- Quasi-Periodic Gaussian Processes
- State-Space Gaussian Processes
- Gaussian Process State-Space Models

---

# 21. Neural-Network Forecasting

## 21.1 Feedforward Networks

- Multilayer Perceptron
- Feedforward Neural Network
- Autoregressive Neural Network
- Neural Network Autoregression (NNAR)
- NAR
- NARX
- NARMAX neural network

## 21.2 Recurrent Networks

- Simple RNN
- Elman Network
- Jordan Network
- LSTM
- Stacked LSTM
- Bidirectional LSTM
- ConvLSTM
- Peephole LSTM
- GRU
- Stacked GRU
- Bidirectional GRU
- Echo State Network
- Reservoir Computing
- Liquid State Machine

## 21.3 Convolutional Networks

- 1D CNN
- Temporal CNN
- Dilated CNN
- Causal CNN
- Temporal Convolutional Network (TCN)
- WaveNet
- CNN-LSTM
- CNN-GRU

---

# 22. Transformer Forecasting Models

- Transformer
- Time-Series Transformer
- Temporal Fusion Transformer (TFT)
- Informer
- Autoformer
- FEDformer
- Pyraformer
- Reformer-based forecasting
- LogTrans
- Crossformer
- PatchTST
- TimesNet
- iTransformer
- TimeMixer
- DLinear
- NLinear
- TiDE
- TSMixer
- TSMixerx
- TimeXer
- ETSformer
- Non-stationary Transformer
- Triformer
- MICN
- LightTS
- SCINet
- FiLM
- FreTS
- Koopa
- ModernTCN
- Chronos
- Lag-Llama
- TimesFM
- Moirai
- TimeGPT-style foundation forecasting models
- decoder-only time-series foundation models
- masked time-series transformers
- probabilistic transformers

---

# 23. Specialized Deep Forecasting Architectures

- DeepAR
- DeepState
- DeepFactor
- DeepVAR
- DeepGLO
- Deep Renewal Process
- N-BEATS
- N-BEATSx
- N-HiTS
- NHITS
- MQ-RNN
- MQRNN
- DeepTCN
- WaveNet forecasting
- Temporal Fusion Transformer
- Neural ODE forecasting
- Latent ODE
- ODE-RNN
- Neural CDE
- Liquid Neural Networks
- State-Space Neural Networks

---

# 24. Neural State-Space / Structured Sequence Models

- Neural State-Space Models
- Deep State-Space Models
- Recurrent State-Space Model
- Deep Kalman Filter
- Variational Recurrent Neural Network
- KalmanNet
- Neural Kalman Filter
- Structured State-Space Sequence Model
- S4
- S4D
- DSS
- S5
- Mamba
- Mamba-2
- selective state-space forecasting models
- Hyena
- RWKV-style recurrent sequence models

---

# 25. Probabilistic Forecasting

- Parametric Distributional Forecasting
- Gaussian Forecasting
- Student-t Forecasting
- Negative Binomial Forecasting
- Poisson Forecasting
- Lognormal Forecasting
- Mixture Density Networks
- Quantile Regression
- Quantile Random Forests
- Quantile Gradient Boosting
- Bayesian Forecasting
- Bayesian Dynamic Linear Models
- Bayesian Structural Time Series
- Bayesian VAR
- Bayesian Neural Networks
- Gaussian Processes
- DeepAR
- DeepState
- DeepVAR
- NGBoost
- Distributional Regression
- GAMLSS
- Conformal Prediction
- Conformalized Quantile Regression
- Jackknife+ predictive intervals
- Bayesian Model Averaging

---

# 26. Bayesian Forecasting Models

- Bayesian Linear Regression
- Bayesian AR
- Bayesian ARMA
- Bayesian ARIMA
- Bayesian VAR
- Bayesian VARMA
- Bayesian VECM
- Bayesian Structural Time Series
- Bayesian Dynamic Linear Model
- Bayesian Dynamic Factor Model
- Bayesian Change-Point Model
- Bayesian Markov-Switching Model
- Bayesian Stochastic Volatility
- Bayesian GARCH
- Gaussian Process
- Bayesian Neural Network
- Bayesian Additive Regression Trees (BART)
- Dynamic BART

---

# 27. Quantile / Distributional Models

- Quantile Regression
- Autoregressive Quantile Regression
- Quantile AR
- Quantile VAR
- Quantile Regression Forest
- Quantile Gradient Boosting
- Quantile Neural Network
- Multi-Quantile RNN
- Distributional Regression
- GAMLSS
- Expectile Regression
- Distributional Random Forest
- NGBoost
- Mixture Density Network

---

# 28. Financial Return Models

- Random Walk
- Random Walk with Drift
- Geometric Brownian Motion
- Arithmetic Brownian Motion
- Ornstein-Uhlenbeck Process
- Mean-Reverting Diffusion
- Vasicek Process
- Cox-Ingersoll-Ross Process
- CEV Process
- Jump Diffusion
- Merton Jump Diffusion
- Kou Double-Exponential Jump Diffusion
- Variance Gamma
- Normal Inverse Gaussian
- Generalized Hyperbolic Process
- Lévy Process
- Stable Distribution Models
- Tempered Stable Process
- CGMY Process
- Heston Model
- Bates Model
- SABR
- Rough Bergomi
- Local Volatility Model
- Local-Stochastic Volatility Model

---

# 29. Interest-Rate / Yield-Curve Forecasting

- Vasicek
- Cox-Ingersoll-Ross
- Hull-White
- Ho-Lee
- Black-Derman-Toy
- Black-Karasinski
- Heath-Jarrow-Morton
- LIBOR Market Model
- Brace-Gatarek-Musiela
- Affine Term Structure Models
- Dynamic Nelson-Siegel
- Dynamic Svensson
- Nelson-Siegel-Svensson
- Arbitrage-Free Nelson-Siegel
- Dynamic Factor Yield-Curve Models
- Gaussian Affine Term Structure Models
- Shadow-Rate Models

---

# 30. Macro / Econometric Forecasting

- AR
- ARIMA
- ARIMAX
- VAR
- BVAR
- VECM
- SVAR
- FAVAR
- GVAR
- Dynamic Factor Model
- DSGE
- Bayesian DSGE
- Semi-Structural Models
- Structural Macro Models
- Local Projections
- Bayesian Local Projections
- MIDAS
- Bridge Equations
- Mixed-Frequency VAR
- Dynamic Stochastic General Equilibrium models
- Agent-Based Macroeconomic Models

---

# 31. Panel Forecasting Models

- Fixed Effects
- Random Effects
- Dynamic Panel Model
- Arellano-Bond
- Blundell-Bond
- Panel VAR
- Panel VECM
- Panel ARDL
- Pooled Mean Group
- Mean Group Estimator
- Common Correlated Effects
- Interactive Fixed Effects
- Dynamic Factor Panel Models
- Hierarchical Bayesian Panel Models

---

# 32. Hierarchical and Grouped Forecasting

- Bottom-Up Forecasting
- Top-Down Forecasting
- Middle-Out Forecasting
- Forecast Reconciliation
- Optimal Combination
- MinT
- Weighted Least Squares Reconciliation
- Ordinary Least Squares Reconciliation
- Structural Scaling
- Variance Scaling
- Probabilistic Hierarchical Forecasting
- Cross-Temporal Reconciliation
- Temporal Hierarchies
- Hierarchical Bayesian Forecasting

---

# 33. Intermittent-Demand Models

- Croston
- Croston-SBA
- Croston-SBJ
- TSB
- HES
- LES
- ADIDA
- IMAPA
- Zero-inflated demand models
- hurdle demand models
- intermittent-demand state-space models

---

# 34. Spectral / Frequency-Domain Forecasting

- Fourier Regression
- Harmonic Regression
- Dynamic Harmonic Regression
- Periodogram-based Forecasting
- Spectral Regression
- Frequency-Domain AR
- Frequency-Domain VAR
- Wavelet Forecasting
- Wavelet-ARIMA
- Wavelet Neural Network
- Hilbert-Huang Transform Forecasting
- EMD Forecasting
- VMD Forecasting
- Singular Spectrum Analysis
- Multitaper Spectral Forecasting

---

# 35. Functional Time-Series Forecasting

- Functional Autoregression
- Functional AR
- Functional ARIMA
- Functional Principal Component Forecasting
- Functional Dynamic Factor Models
- Functional Regression
- Functional Quantile Regression
- Functional State-Space Models
- Curve Forecasting
- Hyndman-Ullah Functional Forecasting

---

# 36. Spatio-Temporal Forecasting

- Spatial Autoregression
- Spatial Error Model
- Spatial Durbin Model
- STAR
- STARMA
- Space-Time ARIMA
- Spatio-Temporal State-Space Model
- Gaussian Process Spatio-Temporal Model
- Kriging
- Dynamic Kriging
- Spatio-Temporal Kriging
- Conditional Autoregressive Models
- Simultaneous Autoregressive Models
- Graph Autoregression
- Graph VAR
- Graph Neural Network Forecasting
- Spatial-Temporal Graph Convolutional Network
- DCRNN
- STGCN
- Graph WaveNet
- MTGNN
- AGCRN
- Temporal Graph Networks

---

# 37. Graph-Based Forecasting

- Graph Autoregressive Model
- Graph Signal Processing Forecasting
- Graph VAR
- Graph Kalman Filter
- Graph Convolutional Network
- Graph Attention Network
- Graph Neural ODE
- Temporal Graph Neural Network
- Spatio-Temporal GNN
- Dynamic Graph Neural Network
- Diffusion Convolutional Recurrent Neural Network
- Graph WaveNet
- Adaptive Graph Convolutional Recurrent Network

---

# 38. Matrix / Tensor Forecasting

- Matrix Autoregression
- Matrix Factor Models
- Dynamic Matrix Factorization
- Tensor Autoregression
- Tensor VAR
- Tensor Factor Models
- Dynamic Tensor Decomposition
- CP-based Forecasting
- Tucker-based Forecasting
- Tensor Train Forecasting
- Low-Rank Matrix Completion Forecasting
- Robust PCA Forecasting
- Dynamic Matrix Completion

---

# 39. Copula-Based Forecasting

- Gaussian Copula Models
- Student-t Copula Models
- Archimedean Copulas
- Clayton Copula
- Gumbel Copula
- Frank Copula
- Vine Copulas
- C-Vine
- D-Vine
- Dynamic Copulas
- Time-Varying Copulas
- Copula-GARCH
- Copula-VAR
- Copula State-Space Models

---

# 40. Extreme-Value / Tail Forecasting

- Generalized Extreme Value
- Peaks Over Threshold
- Generalized Pareto Distribution
- Block Maxima
- Extreme Value Regression
- Dynamic EVT
- GARCH-EVT
- ARMA-EVT
- Conditional EVT
- Multivariate EVT
- Tail Copulas
- Extreme Quantile Regression

---

# 41. Change-Point / Structural-Break Forecasting

- Chow Break Model
- Bai-Perron Multiple Break Model
- CUSUM-based Models
- Bayesian Change-Point Model
- Product Partition Models
- Hidden Markov Change-Point Models
- Online Bayesian Change-Point Detection
- Piecewise Linear Forecasting
- Piecewise AR Models
- Structural-Break ARIMA
- Time-Varying Parameter Models

---

# 42. Local-Projection Models

- Jordà Local Projections
- Linear Local Projections
- Nonlinear Local Projections
- State-Dependent Local Projections
- Smooth Local Projections
- Bayesian Local Projections
- Panel Local Projections
- Quantile Local Projections

---

# 43. Causal / Structural Forecasting

- Structural Equation Models
- Simultaneous Equation Models
- Instrumental Variables Forecasting
- Structural VAR
- Structural VECM
- Local Projections
- Difference-in-Differences with dynamic effects
- Synthetic Control
- Bayesian Structural Time Series
- CausalImpact-style models
- Dynamic Treatment Effect Models
- Structural Causal Models

---

# 44. Ensemble Forecasting

- Simple Average Ensemble
- Weighted Average Ensemble
- Median Ensemble
- Trimmed Mean Ensemble
- Bates-Granger Combination
- Forecast Combination Regression
- Stacking
- Super Learner
- Bayesian Model Averaging
- Dynamic Model Averaging
- Dynamic Model Selection
- Mixture of Experts
- Gating Network
- Boosted Ensemble
- Bagged Forecasting
- Random Forest Ensemble
- Multi-model Ensemble
- Online Ensemble Learning
- Hedge Algorithm
- Exponentially Weighted Forecaster

---

# 45. Hybrid Forecasting

- ARIMA + GARCH
- ARIMA + ANN
- ARIMA + LSTM
- ARIMA + GRU
- ARIMA + SVR
- ARIMA + XGBoost
- ARIMA + Random Forest
- ARIMA + Prophet
- ETS + Neural Network
- STL + ARIMA
- STL + ETS
- STL + machine learning
- Wavelet + ARIMA
- Wavelet + ANN
- Wavelet + LSTM
- EMD + ARIMA
- EMD + LSTM
- VMD + LSTM
- SSA + ARIMA
- State-Space + Neural Network
- GARCH + LSTM
- VAR + Neural Network
- statistical + ML ensemble
- statistical + deep-learning ensemble

---

# 46. Prophet-Type Models

- Prophet
- NeuralProphet
- Additive trend-seasonality-holiday regression
- Piecewise linear trend model
- Piecewise logistic-growth model
- Bayesian additive time-series models

---

# 47. Dynamic Bayesian Networks

- Dynamic Bayesian Network
- Hidden Markov Model
- Bayesian State-Space Model
- Switching Dynamic Bayesian Network
- Conditional Linear Gaussian DBN
- Factorial Hidden Markov Model
- Hierarchical Hidden Markov Model

---

# 48. Fuzzy Forecasting

- Fuzzy Time Series
- First-Order Fuzzy Time Series
- High-Order Fuzzy Time Series
- Weighted Fuzzy Time Series
- Intuitionistic Fuzzy Time Series
- Type-2 Fuzzy Time Series
- Fuzzy AR
- Fuzzy Regression
- Neuro-Fuzzy Forecasting
- ANFIS
- Fuzzy Markov Models

---

# 49. Evolutionary / Metaheuristic Forecasting

Often used to fit, select, or combine forecasting models:

- Genetic Algorithms
- Genetic Programming
- Differential Evolution
- Particle Swarm Optimization
- Ant Colony Optimization
- Simulated Annealing
- Evolution Strategies
- CMA-ES
- Artificial Bee Colony
- Firefly Algorithm
- Grey Wolf Optimizer
- Whale Optimization Algorithm
- Harmony Search

Common hybrids:

- GA-ARIMA
- PSO-ARIMA
- GA-SVR
- PSO-SVR
- GA-LSTM
- PSO-LSTM
- evolutionary neural networks

---

# 50. Chaos / Nonlinear Dynamics Forecasting

- Delay-Coordinate Embedding
- Takens Embedding
- Local Constant Predictor
- Local Linear Predictor
- Analog Method
- Nearest-Neighbor Prediction
- Recurrence-Based Prediction
- Echo State Networks
- Reservoir Computing
- Lyapunov-Based Forecasting
- Koopman Operator Forecasting
- Dynamic Mode Decomposition
- Extended Dynamic Mode Decomposition
- Hankel DMD

---

# 51. Koopman / Operator-Theoretic Forecasting

- Koopman Operator
- Koopman Mode Decomposition
- Dynamic Mode Decomposition (DMD)
- Extended DMD
- Kernel DMD
- Hankel DMD
- Higher-Order DMD
- Streaming DMD
- Neural Koopman Models
- Deep Koopman Networks
- Koopman Autoencoders

---

# 52. Physics-Informed Forecasting

- Physics-Informed Neural Networks
- Neural ODEs
- Universal Differential Equations
- Physics-Informed Gaussian Processes
- Hybrid Mechanistic / Statistical Models
- Grey-Box State-Space Models
- Digital Twin Forecasting
- PDE-constrained forecasting
- Data Assimilation Models
- Ensemble Kalman Forecasting

---

# 53. Agent-Based and Simulation Forecasts

- Agent-Based Models
- Monte Carlo Simulation
- Microsimulation
- Discrete-Event Simulation
- System Dynamics
- Cellular Automata
- Markov Simulation
- Scenario Simulation
- Bootstrapped Simulation
- Historical Simulation
- Stress-Test Models

---

# 54. Monte Carlo and Stochastic Simulation

- Monte Carlo Forecasting
- Bootstrap Forecasting
- Residual Bootstrap
- Block Bootstrap
- Moving Block Bootstrap
- Stationary Bootstrap
- Parametric Bootstrap
- Sequential Monte Carlo
- Markov Chain Monte Carlo
- Quasi-Monte Carlo
- Importance Sampling
- Latin Hypercube Sampling

---

# 55. Forecasting with Large Foundation Models

- Time-Series Foundation Models
- pretrained autoregressive time-series models
- pretrained masked time-series models
- zero-shot forecasting models
- few-shot forecasting models
- Chronos-family models
- TimesFM-family models
- Moirai-family models
- Lag-Llama-family models
- TimeGPT-style models
- LLM-assisted forecasting
- multimodal time-series foundation models
- text-conditioned forecasting models

---

# 56. Specialized Financial Forecasting Structures

## Price / Return

- ARIMA
- ARFIMA
- VAR
- VECM
- GARCH family
- stochastic volatility
- regime-switching
- jump diffusion
- Lévy process
- state-space models
- machine-learning regressors
- neural sequence models
- transformers

## Volatility

- Historical Volatility
- EWMA
- ARCH
- GARCH
- EGARCH
- GJR-GARCH
- APARCH
- FIGARCH
- Realized GARCH
- HAR-RV
- Stochastic Volatility
- Rough Volatility

## Correlation / Covariance

- Rolling covariance
- EWMA covariance
- CCC-GARCH
- DCC-GARCH
- BEKK-GARCH
- Factor covariance models
- stochastic covariance models
- Wishart models
- dynamic copulas

## Market Microstructure

- ACD
- Hawkes processes
- Autoregressive Conditional Intensity models
- duration models
- order-flow autoregression
- signed-volume models
- state-space microstructure models
- DeepLOB-type models
- order-book transformers

---

# 57. Common ARIMA-Family Naming Map

| Model | Meaning |
|---|---|
| AR | Autoregressive |
| MA | Moving Average |
| ARMA | Autoregressive Moving Average |
| ARIMA | Autoregressive Integrated Moving Average |
| SARIMA | Seasonal ARIMA |
| ARIMAX | ARIMA with exogenous regressors |
| SARIMAX | Seasonal ARIMA with exogenous regressors |
| ARFIMA | Autoregressive Fractionally Integrated Moving Average |
| VAR | Vector Autoregression |
| VARMA | Vector Autoregressive Moving Average |
| VARIMA | Vector Autoregressive Integrated Moving Average |
| VARMAX | VARMA with exogenous regressors |
| VECM | Vector Error Correction Model |
| ARDL | Autoregressive Distributed Lag |
| NARDL | Nonlinear ARDL |
| TAR | Threshold Autoregression |
| SETAR | Self-Exciting Threshold Autoregression |
| STAR | Smooth Transition Autoregression |
| LSTAR | Logistic Smooth Transition Autoregression |
| ESTAR | Exponential Smooth Transition Autoregression |
| MS-AR | Markov-Switching Autoregression |
| MS-VAR | Markov-Switching VAR |

---

# 58. Model Classification by Forecasting Target

## Point Forecast

- ARIMA
- ETS
- VAR
- regression
- Random Forest
- XGBoost
- LSTM
- Transformer
- N-BEATS

## Interval Forecast

- ARIMA predictive intervals
- ETS intervals
- state-space models
- Gaussian Processes
- Bayesian models
- bootstrap forecasts
- conformal prediction

## Density Forecast

- Bayesian models
- stochastic volatility
- mixture density networks
- DeepAR
- NGBoost
- probabilistic transformers

## Quantile Forecast

- Quantile Regression
- Quantile Random Forest
- LightGBM quantile
- gradient boosting quantile
- MQ-RNN
- TFT quantile output
- conformalized quantile regression

---

# 59. Classification by Horizon

## Very Short Horizon / High Frequency

- AR
- VAR
- state-space
- Kalman filter
- GARCH
- Hawkes process
- ACD
- order-book neural networks
- TCN
- transformers
- graph neural networks

## Short / Medium Horizon

- ARIMA
- SARIMA
- ETS
- VAR
- dynamic regression
- boosting
- LSTM
- N-BEATS
- TFT

## Long Horizon

- trend models
- structural time series
- dynamic factor models
- cointegration models
- DSGE
- long-memory models
- transformers
- foundation time-series models

---

# 60. Classification by Data Frequency

- Tick-by-tick models
- event-time models
- transaction-time models
- second-level models
- minute-level models
- intraday models
- daily models
- weekly models
- monthly models
- quarterly models
- annual models
- mixed-frequency models
- irregularly sampled time-series models

---

# 61. Model Selection / Forecast Evaluation

Common model-selection criteria:

- AIC
- AICc
- BIC
- HQIC
- Mallows Cp
- adjusted R²
- cross-validation
- rolling-origin evaluation
- expanding-window validation
- blocked time-series CV
- prequential evaluation

Forecast-loss / accuracy measures:

- MAE
- MSE
- RMSE
- RMSLE
- MAPE
- sMAPE
- WAPE
- MASE
- RMSSE
- MdAE
- pinball loss
- quantile loss
- CRPS
- log score
- Brier score
- Winkler score
- interval coverage
- Diebold-Mariano test
- Giacomini-White test
- Model Confidence Set

---

# 62. Compact Core Forecasting Stack

If reducing the entire taxonomy to a practical core set:

1. Naive / seasonal naive
2. ETS / Holt-Winters
3. AR
4. MA
5. ARMA
6. ARIMA
7. SARIMA
8. ARIMAX / SARIMAX
9. ARFIMA
10. VAR
11. VECM
12. BVAR
13. Dynamic Factor Model
14. State-Space / Kalman Filter
15. Structural Time Series / BSTS
16. GARCH
17. EGARCH
18. GJR-GARCH
19. DCC-GARCH
20. Stochastic Volatility
21. Markov-Switching Models
22. TAR / SETAR / STAR
23. MIDAS
24. HAR-RV
25. Gaussian Process
26. Random Forest
27. XGBoost / LightGBM / CatBoost
28. SVR
29. LSTM / GRU
30. TCN
31. N-BEATS / N-HiTS
32. Temporal Fusion Transformer
33. PatchTST / iTransformer / related transformers
34. Time-series foundation models
35. Hawkes Process
36. Dynamic Copula Models
37. Ensemble / Model Averaging
38. Hybrid statistical + ML models

---

# 63. ARIMA-Centered Lineage

```text
White Noise
   |
   +-- MA(q)
   |
   +-- AR(p)
         |
         +-- ARMA(p,q)
                |
                +-- ARIMA(p,d,q)
                |      |
                |      +-- SARIMA
                |      |
                |      +-- ARIMAX
                |      |
                |      +-- SARIMAX
                |      |
                |      +-- ARFIMA / FARIMA
                |      |
                |      +-- ARIMA-GARCH
                |      |
                |      +-- regime-switching ARIMA
                |
                +-- VARMA
                       |
                       +-- VARIMA
                       |
                       +-- VARMAX
                       |
                       +-- VECM when cointegrated
```

---

# 64. Financial-Econometric Lineage

```text
Returns / Levels
|
+-- AR / ARMA / ARIMA / ARFIMA
|
+-- VAR / VECM / BVAR / SVAR
|
+-- State-Space / Dynamic Factor
|
+-- Regime Switching
|
+-- Nonlinear AR / TAR / STAR
|
+-- ML / Deep Learning
|
+-- Ensembles

Conditional Variance
|
+-- ARCH
     |
     +-- GARCH
          |
          +-- IGARCH
          +-- EGARCH
          +-- GJR-GARCH
          +-- APARCH
          +-- FIGARCH
          +-- Realized GARCH
          +-- DCC / BEKK / CCC

Latent Volatility
|
+-- Stochastic Volatility
     |
     +-- SV leverage
     +-- SV jumps
     +-- Factor SV
     +-- Rough volatility

Events / Trades
|
+-- ACD
+-- Hawkes
+-- point processes
+-- order-flow / order-book models
```

---

# 65. Notes on Terminology

- **ARIMA** models conditional mean dynamics after differencing a nonstationary process.
- **SARIMA** adds seasonal autoregressive, differencing, and moving-average components.
- **ARIMAX/SARIMAX** add external predictors.
- **ARFIMA** replaces integer differencing with fractional differencing and is used for long memory.
- **VAR/VECM** generalize autoregression to multiple interacting time series.
- **GARCH-family models** primarily forecast conditional variance or volatility rather than the conditional mean.
- **State-space models** represent latent states that evolve dynamically and generate observations.
- **Markov-switching models** allow parameters to change across latent regimes.
- **ML/deep-learning models** generally learn nonlinear mappings from lagged values and covariates without requiring the same explicit stochastic-process assumptions as classical models.
- **Probabilistic forecasting** predicts a distribution, interval, or set of quantiles rather than only a single point estimate.

