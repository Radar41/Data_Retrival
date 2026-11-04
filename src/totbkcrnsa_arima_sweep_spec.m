function sweepSpec = totbkcrnsa_arima_sweep_spec(projectRoot)

arguments
    projectRoot (1,1) string
end

sweepSpec = struct();

sweepSpec.family = "nonseasonal_arima";

sweepSpec.base_config = ...
    totbkcrnsa_arima_110_evaluation_config(projectRoot);

sweepSpec.arima_p_values = 0:4;
sweepSpec.arima_d_values = 0:2;
sweepSpec.arima_q_values = 0:4;

sweepSpec.maximum_arima_order_sum = 5;

sweepSpec.constant_policy = "estimate";

sweepSpec.exclude_all_zero_order = true;

end