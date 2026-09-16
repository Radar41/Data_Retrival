function adapter = create_model_adapter(modelConfig)

arguments
    modelConfig (1,1) struct
end

assert(isfield(modelConfig, "adapter_id"), ...
    "modelConfig.adapter_id is required.");

adapterId = string(modelConfig.adapter_id);

assert(isscalar(adapterId) && ~ismissing(adapterId) && ...
    strlength(adapterId) > 0, ...
    "modelConfig.adapter_id must be one nonempty scalar string.");

switch adapterId
    case "analytical.naive_random_walk"
        adapter = gdss.AnalyticalNaiveRandomWalkAdapter(modelConfig);

    case "matlab.ssm.local_level"
        adapter = gdss.MatlabSsmLocalLevelAdapter(modelConfig);

    case "matlab.ssm.local_linear_trend"
        adapter = gdss.MatlabSsmLocalLinearTrendAdapter(modelConfig);

    case "matlab.ssm.damped_trend"
        adapter = gdss.MatlabSsmDampedTrendAdapter(modelConfig);

    otherwise
        error( ...
            "gdss:create_model_adapter:UnsupportedAdapterId", ...
            "Unsupported modelConfig.adapter_id: %s", adapterId);
end

end