function evaluationRun = run_totbkcrnsa_naive_evaluation(config)

arguments
    config (1,1) struct
end

assert(isequal(string(config.adapter_id), ...
    "analytical.naive_random_walk"), ...
    "This reference evaluator requires adapter_id analytical.naive_random_walk.");

assert(isequal(string(config.series_id), "TOTBKCRNSA"), ...
    "This reference evaluator requires series_id TOTBKCRNSA.");

assert(isequal(string(config.data_variant), "LEVEL"), ...
    "This reference evaluator requires data_variant LEVEL.");

assert(isequal(string(config.target_transform), "identity"), ...
    "This function requires the identity target transform.");

evaluationRun = run_gdss_evaluation(config);

end