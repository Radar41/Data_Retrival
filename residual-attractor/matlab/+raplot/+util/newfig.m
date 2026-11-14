function [f, tl] = newfig(w, h, rows, cols, ttl, ctx)
%NEWFIG  Invisible white figure of w x h pixels with a rows x cols tiledlayout and a title
% that always carries the build id. Text is never TeX-interpreted (ids have underscores).
f = figure('Visible', 'off', 'Units', 'pixels', 'Position', [0 0 w h], 'Color', 'w', ...
    'defaultTextInterpreter', 'none', 'defaultAxesTickLabelInterpreter', 'none', ...
    'defaultLegendInterpreter', 'none', 'defaultAxesFontSize', 8, 'defaultTextFontSize', 8, ...
    'defaultColorbarTickLabelInterpreter', 'none');
tl = tiledlayout(f, rows, cols, 'TileSpacing', 'compact', 'Padding', 'compact');
title(tl, ttl, 'Interpreter', 'none', 'FontSize', 11, 'FontWeight', 'bold');
subtitle(tl, "build " + ctx.id, 'Interpreter', 'none', 'FontSize', 8, 'Color', [.4 .4 .4]);
end
