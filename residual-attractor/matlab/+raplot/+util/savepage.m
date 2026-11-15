function savepage(f, file)
%SAVEPAGE  Write figure f to file as PNG at its full pixel size (no cropping) and close it,
% so every page drawn at the same figure size has the same width x height.
try
    exportgraphics(f, file, 'Resolution', 96, 'Padding', 'figure');
catch
    f.PaperPositionMode = 'auto';
    print(f, file, '-dpng', '-r96');
end
close(f);
end
