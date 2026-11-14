function savefig(f, ctx, name)
%SAVEFIG  Write figure f to <stage dir>/<name> as PNG and close it.
exportgraphics(f, fullfile(ctx.out, name), 'Resolution', 96);
close(f);
end
