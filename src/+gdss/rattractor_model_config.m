function mc = rattractor_model_config(c)
%RATTRACTOR_MODEL_CONFIG  One residual-attractor request configuration -> the modelConfig gdss.create_model_adapter takes.
%   c.config_id, c.method, c.adapter_id, c.params (struct). Every params field that is not part of the
%   estimation policy (refit_every, window, min_train) is copied onto modelConfig under its own name,
%   so a registry YAML names adapter fields directly (arima_p, ets_trend, boost_lags, ...).
% Rattractor ingest has already transformed the series, so the adapter sees the target as is.
POLICY = ["refit_every", "window", "min_train"];
mc = struct();
mc.adapter_id = string(c.adapter_id);
mc.model_id = string(c.config_id);
mc.series_id = "rattractor";
mc.data_variant = "rattractor";
mc.target_transform = "identity";
mc.forecast_strategy = "recursive";
mc.forecast_scale = "target";
mc.prediction_interval_levels = [0.8 0.95];
f = fieldnames(c.params);
for n = 1:numel(f)
    if ismember(f{n}, POLICY), continue; end
    v = c.params.(f{n});
    if ischar(v), v = string(v); end
    mc.(f{n}) = v;
end
assert(string(c.params.window) == "expanding", 'gdss:rattractor:window', ...
    'config %s: only the expanding window is implemented', c.config_id);
end
