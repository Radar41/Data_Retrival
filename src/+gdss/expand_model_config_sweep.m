function modelConfigs = expand_model_config_sweep(sweepSpec)

arguments
    sweepSpec (1,1) struct
end

assert(isfield(sweepSpec, "family"), ...
    "sweepSpec.family is required.");

assert(isfield(sweepSpec, "base_config"), ...
    "sweepSpec.base_config is required.");

family = string(sweepSpec.family);

assert(isscalar(family) && ~ismissing(family) && ...
    strlength(family) > 0, ...
    "sweepSpec.family must be one nonempty scalar string.");

assert(isstruct(sweepSpec.base_config) && ...
    isscalar(sweepSpec.base_config), ...
    "sweepSpec.base_config must be one scalar struct.");

switch family

    case "nonseasonal_arima"
        modelConfigs = expandNonseasonalArimaSweep(sweepSpec);

    otherwise
        error( ...
            "gdss:expand_model_config_sweep:UnsupportedFamily", ...
            "Unsupported sweepSpec.family: %s", family);
end

end


function modelConfigs = expandNonseasonalArimaSweep(sweepSpec)

requiredFields = [ ...
    "arima_p_values"
    "arima_d_values"
    "arima_q_values"];

for i = 1:numel(requiredFields)

    fieldName = requiredFields(i);

    assert(isfield(sweepSpec, fieldName), ...
        "Nonseasonal ARIMA sweep requires sweepSpec." + ...
        fieldName + ".");
end

pValues = validateOrderValues( ...
    sweepSpec.arima_p_values, ...
    "sweepSpec.arima_p_values");

dValues = validateOrderValues( ...
    sweepSpec.arima_d_values, ...
    "sweepSpec.arima_d_values");

qValues = validateOrderValues( ...
    sweepSpec.arima_q_values, ...
    "sweepSpec.arima_q_values");

if isfield(sweepSpec, "maximum_arima_order_sum")

    maximumOrderSum = sweepSpec.maximum_arima_order_sum;

    assert(isnumeric(maximumOrderSum) && ...
        isscalar(maximumOrderSum) && ...
        isfinite(maximumOrderSum) && ...
        maximumOrderSum >= 0 && ...
        maximumOrderSum == floor(maximumOrderSum), ...
        "sweepSpec.maximum_arima_order_sum must be one " + ...
        "nonnegative integer.");

else
    maximumOrderSum = Inf;
end

if isfield(sweepSpec, "exclude_all_zero_order")

    excludeAllZeroOrder = sweepSpec.exclude_all_zero_order;

    assert(islogical(excludeAllZeroOrder) && ...
        isscalar(excludeAllZeroOrder), ...
        "sweepSpec.exclude_all_zero_order must be logical scalar.");

else
    excludeAllZeroOrder = false;
end

if isfield(sweepSpec, "constant_policy")

    constantPolicy = string(sweepSpec.constant_policy);

    assert(isscalar(constantPolicy) && ...
        ~ismissing(constantPolicy) && ...
        any(constantPolicy == ["estimate"; "exclude"]), ...
        "sweepSpec.constant_policy must be ""estimate"" or ""exclude"".");

else
    constantPolicy = "estimate";
end

baseConfig = sweepSpec.base_config;

assert(isfield(baseConfig, "adapter_id") && ...
    string(baseConfig.adapter_id) == "matlab.arima", ...
    "Nonseasonal ARIMA sweep base_config.adapter_id must be matlab.arima.");

assert(isfield(baseConfig, "series_id"), ...
    "base_config.series_id is required.");

assert(isfield(baseConfig, "data_variant"), ...
    "base_config.data_variant is required.");

assert(isfield(baseConfig, "target_transform"), ...
    "base_config.target_transform is required.");

candidateCount = ...
    numel(pValues) * numel(dValues) * numel(qValues);

% Do not preallocate from baseConfig.
% Generated candidates add ARIMA-specific metadata fields that may not
% exist in baseConfig, which would cause a dissimilar-structure error.
modelConfigs = struct.empty(0, 1);

acceptedCount = 0;

for pIndex = 1:numel(pValues)

    p = pValues(pIndex);

    for dIndex = 1:numel(dValues)

        d = dValues(dIndex);

        for qIndex = 1:numel(qValues)

            q = qValues(qIndex);

            if p + d + q > maximumOrderSum
                continue
            end

            if excludeAllZeroOrder && p == 0 && d == 0 && q == 0
                continue
            end

            acceptedCount = acceptedCount + 1;

            currentConfig = baseConfig;

            currentConfig.adapter_id = "matlab.arima";

            currentConfig.arima_p = p;
            currentConfig.arima_d = d;
            currentConfig.arima_q = q;

            currentConfig.model_family = "nonseasonal_arima";

            currentConfig.structure_id = ...
                "arima_" + string(p) + string(d) + string(q);

            currentConfig.model_id = ...
                string(baseConfig.series_id) + "_" + ...
                lower(string(baseConfig.data_variant)) + "_" + ...
                currentConfig.structure_id + "_v1";

            currentConfig.state_representation = ...
                "backend_arima_state";

            currentConfig.state_dimension = NaN;
            currentConfig.state_components = strings(0, 1);

            currentConfig.transition_engine = ...
                "nonseasonal_arima_lag_polynomial";

            currentConfig.observation_engine = ...
                "arima_observation_equation";

            currentConfig.state_update_mode = "backend_native";
            currentConfig.initialization_policy = "backend_default";

            currentConfig.estimation_method = ...
                "maximum_likelihood";

            currentConfig.estimate_parameters = true;

            currentConfig.parameter_schema = ...
                arimaParameterSchema(p, q, constantPolicy);

            currentConfig.fixed_parameters = ...
                arimaFixedParameters(constantPolicy);

            currentConfig.estimated_parameters = ...
                arimaEstimatedParameters(p, q, constantPolicy);

            currentConfig.parameter_constraints = ...
                "ar_stationarity_ma_invertibility_and_" + ...
                "nonnegative_innovation_variance";

            currentConfig.minimum_training_observations = ...
                max(10, p + d + q + 5);

            currentConfig.forecast_distribution_kind = "normal";

            currentConfig.forecast_distribution_method = ...
                "arima_forecast_mse";

            currentConfig.prediction_interval_method = ...
                "normal_quantile";

            % First admissible model establishes the full struct schema.
            if acceptedCount == 1
                modelConfigs = currentConfig;
            else
                modelConfigs(acceptedCount, 1) = currentConfig;
            end
        end
    end
end

assert(~isempty(modelConfigs), ...
    "Sweep constraints produced zero admissible ARIMA configurations.");

% Defensive check: all accepted configurations must be retained.
assert(numel(modelConfigs) == acceptedCount, ...
    "Accepted ARIMA configuration count does not match output count.");

% candidateCount is deliberately retained as a documented upper bound.
assert(acceptedCount <= candidateCount, ...
    "Accepted configuration count exceeds candidate count.");

modelIds = string({modelConfigs.model_id})';

assert(numel(unique(modelIds)) == numel(modelIds), ...
    "Sweep expansion produced duplicate model_id values.");

structureIds = string({modelConfigs.structure_id})';

assert(numel(unique(structureIds)) == numel(structureIds), ...
    "Sweep expansion produced duplicate structure_id values.");

end


function values = validateOrderValues(values, fieldLabel)

assert(isnumeric(values) && isvector(values) && ~isempty(values), ...
    fieldLabel + " must be a nonempty numeric vector.");

values = unique(double(values(:)))';

assert(all(isfinite(values)) && ...
    all(values >= 0) && ...
    all(values == floor(values)), ...
    fieldLabel + " must contain nonnegative integers only.");

end


function parameterSchema = arimaParameterSchema(p, q, constantPolicy)

parameterSchema = strings(0, 1);

if constantPolicy == "estimate"
    parameterSchema(end + 1, 1) = "constant";
end

for lag = 1:p
    parameterSchema(end + 1, 1) = "ar_" + string(lag);
end

for lag = 1:q
    parameterSchema(end + 1, 1) = "ma_" + string(lag);
end

parameterSchema(end + 1, 1) = "innovation_variance";

end


function fixedParameters = arimaFixedParameters(constantPolicy)

fixedParameters = struct();

if constantPolicy == "exclude"
    fixedParameters.constant = 0;
end

end


function estimatedParameters = arimaEstimatedParameters( ...
    p, q, constantPolicy)

estimatedParameters = arimaParameterSchema(p, q, constantPolicy);

if constantPolicy == "exclude"
    estimatedParameters(estimatedParameters == "constant") = [];
end

end