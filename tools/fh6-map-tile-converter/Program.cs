using System.IO.Compression;
using System.Text.Json;
using System.Text.RegularExpressions;
using ForzaTelemetryTracker.FH6MapTileConverter.Swatchbin;

namespace ForzaTelemetryTracker.FH6MapTileConverter;

internal static partial class Program
{
    private const int Success = 0;
    private const int InvalidArguments = 2;
    private const int InvalidInputArchive = 3;
    private const int UnsupportedTextureFormat = 4;
    private const int ConversionFailed = 5;
    private const string TileCoordinateSystem = "fh6-row-column-v1";

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        WriteIndented = true,
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    };

    public static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0)
            {
                PrintUsage();
                return InvalidArguments;
            }

            var command = args[0].ToLowerInvariant();
            var options = ParseOptions(args.Skip(1).ToArray());
            return command switch
            {
                "inspect-zip" => InspectZip(options),
                "convert-zip" => ConvertZip(options),
                _ => Fail(InvalidArguments, $"Unknown command: {args[0]}"),
            };
        }
        catch (ArgumentException ex)
        {
            return Fail(InvalidArguments, ex.Message);
        }
        catch (InvalidDataException ex)
        {
            return Fail(InvalidInputArchive, ex.Message);
        }
        catch (FileNotFoundException ex)
        {
            return Fail(InvalidInputArchive, ex.Message);
        }
        catch (NotSupportedException ex)
        {
            return Fail(UnsupportedTextureFormat, ex.Message);
        }
        catch (Exception ex)
        {
            return Fail(ConversionFailed, ex.ToString());
        }
    }

    private static int InspectZip(Dictionary<string, string> options)
    {
        var inputPath = RequirePath(options, "input");
        if (!File.Exists(inputPath))
        {
            return Fail(InvalidInputArchive, $"Input archive does not exist: {inputPath}");
        }

        var entries = ReadTileInfos(inputPath);
        Console.WriteLine(JsonSerializer.Serialize(new { entries }, JsonOptions));
        return Success;
    }

    private static int ConvertZip(Dictionary<string, string> options)
    {
        var inputPath = RequirePath(options, "input");
        var outputPath = RequirePath(options, "output");
        var manifestPath = RequirePath(options, "manifest");
        var format = options.GetValueOrDefault("format", "png").ToLowerInvariant();

        if (format != "png")
        {
            return Fail(InvalidArguments, $"Unsupported output format: {format}. Only png is supported.");
        }

        if (!File.Exists(inputPath))
        {
            return Fail(InvalidInputArchive, $"Input archive does not exist: {inputPath}");
        }

        var tileInfos = ReadTileInfos(inputPath);
        var unsupported = tileInfos
            .Where(t => t.IsDurango || t.Width == 0 || t.Height == 0 || !BcnPngWriter.IsSupported((uint)t.DxgiFormat))
            .ToList();
        if (unsupported.Count > 0)
        {
            foreach (var tile in unsupported)
            {
                Console.Error.WriteLine($"Unsupported tile {tile.Entry}: durango={tile.IsDurango}, {tile.Width}x{tile.Height}, dxgi={tile.DxgiFormat}");
            }

            return UnsupportedTextureFormat;
        }

        Directory.CreateDirectory(outputPath);

        var failures = new List<string>();
        using var archive = ZipFile.OpenRead(inputPath);
        var reader = new SwatchbinReader();
        foreach (var tile in tileInfos)
        {
            try
            {
                var entry = archive.GetEntry(tile.Entry);
                if (entry is null)
                {
                    failures.Add($"{tile.Entry}: entry disappeared during conversion");
                    continue;
                }

                using var memory = new MemoryStream();
                using (var entryStream = entry.Open())
                {
                    entryStream.CopyTo(memory);
                }

                memory.Position = 0;
                var info = reader.Load(memory, tile.Entry);
                var destination = Path.Combine(outputPath, tile.Z.ToString(), tile.X.ToString(), $"{tile.Y}.png");
                BcnPngWriter.WritePng(info, destination);
            }
            catch (Exception ex)
            {
                failures.Add($"{tile.Entry}: {ex.Message}");
            }
        }

        if (failures.Count > 0)
        {
            foreach (var failure in failures)
            {
                Console.Error.WriteLine(failure);
            }

            return ConversionFailed;
        }

        var manifest = BuildManifest(inputPath, format, tileInfos);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(manifestPath))!);
        File.WriteAllText(manifestPath, JsonSerializer.Serialize(manifest, JsonOptions));
        return Success;
    }

    private static IReadOnlyList<TileInspectionEntry> ReadTileInfos(string inputPath)
    {
        using var archive = ZipFile.OpenRead(inputPath);
        var reader = new SwatchbinReader();
        var entries = new List<TileInspectionEntry>();

        foreach (var entry in archive.Entries.Where(e => e.FullName.EndsWith(".swatchbin", StringComparison.OrdinalIgnoreCase)))
        {
            var tile = ParseTileEntryName(entry.FullName);
            using var memory = new MemoryStream();
            using (var entryStream = entry.Open())
            {
                entryStream.CopyTo(memory);
            }

            memory.Position = 0;
            var info = reader.Load(memory, entry.FullName);
            entries.Add(new TileInspectionEntry(
                entry.FullName,
                tile.Z,
                tile.X,
                tile.Y,
                checked((int)info.Width),
                checked((int)info.Height),
                checked((int)info.DxgiFormat),
                info.DxgiFormatName,
                info.IsDurangoFormat,
                info.RawTextureData.Length));
        }

        if (entries.Count == 0)
        {
            throw new InvalidDataException($"No .swatchbin tile entries found in {inputPath}.");
        }

        return entries
            .OrderBy(e => e.Z)
            .ThenBy(e => e.Y)
            .ThenBy(e => e.X)
            .ToList();
    }

    private static TileCoordinate ParseTileEntryName(string entryName)
    {
        var fileName = Path.GetFileName(entryName).Replace('\\', '/');
        var match = TileEntryRegex().Match(fileName);
        if (!match.Success)
        {
            throw new InvalidDataException($"Tile entry name must match '<z>-<row>-<column>.swatchbin': {entryName}");
        }

        var row = int.Parse(match.Groups["row"].Value);
        var column = int.Parse(match.Groups["column"].Value);

        return new TileCoordinate(
            int.Parse(match.Groups["z"].Value),
            column,
            row);
    }

    private static MapTileManifest BuildManifest(
        string inputPath,
        string format,
        IReadOnlyList<TileInspectionEntry> tileInfos)
    {
        var mapMetadata = MapMetadataFromInput(inputPath);
        return new MapTileManifest(
            "fh6",
            mapMetadata.Map,
            mapMetadata.Season,
            format,
            tileInfos.Max(t => t.Width),
            tileInfos.Min(t => t.Z),
            tileInfos.Max(t => t.Z),
            TileCoordinateSystem,
            tileInfos.Select(t => new MapTileManifestEntry(t.Z, t.X, t.Y, $"{t.Z}/{t.X}/{t.Y}.png")).ToList());
    }

    private static (string Map, string Season) MapMetadataFromInput(string inputPath)
    {
        var name = Path.GetFileNameWithoutExtension(inputPath);
        var match = MapZipRegex().Match(name);
        if (!match.Success)
        {
            return ("brio", "summer");
        }

        return (match.Groups["map"].Value.ToLowerInvariant(), match.Groups["season"].Value.ToLowerInvariant());
    }

    private static Dictionary<string, string> ParseOptions(string[] args)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < args.Length; i++)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"Unexpected argument: {args[i]}");
            }

            var key = args[i][2..];
            if (string.IsNullOrWhiteSpace(key))
            {
                throw new ArgumentException("Empty option name.");
            }

            if (i + 1 >= args.Length || args[i + 1].StartsWith("--", StringComparison.Ordinal))
            {
                throw new ArgumentException($"Missing value for --{key}.");
            }

            result[key] = args[++i];
        }

        return result;
    }

    private static string RequirePath(Dictionary<string, string> options, string key)
    {
        if (!options.TryGetValue(key, out var value) || string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException($"Missing required option --{key}.");
        }

        return value;
    }

    private static int Fail(int exitCode, string message)
    {
        Console.Error.WriteLine(message);
        return exitCode;
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine("Usage:");
        Console.Error.WriteLine("  forza-map-tile-converter inspect-zip --input <Map_Brio_Season.zip>");
        Console.Error.WriteLine("  forza-map-tile-converter convert-zip --input <Map_Brio_Season.zip> --output <dir> --format png --manifest <manifest.json>");
    }

    [GeneratedRegex(@"^(?<z>\d+)-(?<row>\d+)-(?<column>\d+)\.swatchbin$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex TileEntryRegex();

    [GeneratedRegex(@"^Map_(?<map>[^_]+)_(?<season>[^_]+)$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex MapZipRegex();

    private sealed record TileCoordinate(int Z, int X, int Y);

    private sealed record TileInspectionEntry(
        string Entry,
        int Z,
        int X,
        int Y,
        int Width,
        int Height,
        int DxgiFormat,
        string DxgiFormatName,
        bool IsDurango,
        int RawByteCount);

    private sealed record MapTileManifest(
        string Game,
        string Map,
        string Season,
        string Format,
        int TileSize,
        int MinZoom,
        int MaxZoom,
        string TileCoordinateSystem,
        IReadOnlyList<MapTileManifestEntry> Tiles);

    private sealed record MapTileManifestEntry(int Z, int X, int Y, string Path);
}
