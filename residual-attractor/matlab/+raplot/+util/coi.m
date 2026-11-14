function coi(ax, x, y, incoi)
%COI  Shade the cells outside the cone of influence (incoi false) of an imagesc on ax, and draw the cone edge.
hold(ax, 'on');
sh = image(ax, x, y, repmat(reshape([1 1 1], 1, 1, 3), size(incoi)));
set(sh, 'AlphaData', 0.55 * double(~incoi));
if any(~incoi(:)) && any(incoi(:))
    contour(ax, x, y, double(incoi), [0.5 0.5], 'Color', [.3 .3 .3], 'LineStyle', ':', 'LineWidth', 0.6);
end
end
