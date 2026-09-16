function config = totbkcrnsa_local_level_ssm_evaluation_config(projectRoot)

arguments
    projectRoot (1,1) string
end

config = struct();

config.adapter_id = "matlab.ssm.local_level";

config.model_id = "totbkcrnsa_level_local_level_ssm_v1";
config.model_family = "gdss_linear_gaussian_state_space";
config.structure_id = "local_level";
config.schema_version = "v1";

config.normalized_csv_path = fullfile( ...
    projectRoot, ...
    "data", "staging", "normalized", "fred", "validation", ...
    "fred_public_datalist_banks_weekly_bfaf15972702", ...
    "normalized_weekly_ending_wednesday.csv");

config.source_member = "weekly,_ending_wednesday.csv";
config.series_id = "TOTBKCRNSA";
config.data_variant = "LEVEL";
config.target_transform = "identity";
config.origin_index = 2539;

config.target_dimension = 1;
config.forecast_strategy = "recursive";
config.forecast_scale = "LEVEL";

config.state_representation = "latent_local_level";
config.state_dimension = 1;
config.state_components = "level";

config.transition_engine = "linear_gaussian_random_walk";
config.observation_engine = "linear_gaussian_direct_observation";
config.state_update_mode = "kalman_filter";

config.initialization_policy = "diffuse";
config.estimation_method = "maximum_likelihood";
config.estimate_parameters = true;

config.parameter_schema = [ ...
    "state_disturbance_variance"
    "observation_disturbance_variance"];

config.fixed_parameters = struct();
config.estimated_parameters = [ ...
    "state_disturbance_variance"
    "observation_disturbance_variance"];

config.parameter_constraints = ...
    "variances_nonnegative";

config.training_window_policy = "expanding";
config.minimum_training_observations = 2;
config.missing_value_policy = "reject_nonfinite";

config.forecast_distribution_kind = "normal";
config.forecast_distribution_method = "ssm_forecast_mse";

config.prediction_interval_levels = [0.80 0.95];
config.prediction_interval_method = "normal_quantile";

config.residual_kind = "forecast_error";
config.residual_formula = "actual_value_minus_point_forecast";
config.residual_scale = "LEVEL";

end