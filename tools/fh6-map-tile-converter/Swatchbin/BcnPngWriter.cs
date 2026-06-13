using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using BCnEncoder.Decoder;
using BCnEncoder.Shared;

namespace ForzaTelemetryTracker.FH6MapTileConverter.Swatchbin;

public static class BcnPngWriter
{
    public static bool IsSupported(uint dxgiFormat) =>
        BcnFormatFor(dxgiFormat) != CompressionFormat.Unknown || dxgiFormat is 28 or 29 or 87;

    public static void WritePng(SwatchbinInfo info, string path)
    {
        if (info.IsDurangoFormat)
        {
            throw new NotSupportedException("Durango/Xbox tiled swatchbins are not supported by this converter path.");
        }

        var rgba = DecodeToRgba(info);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        SaveRgbaPng(rgba, checked((int)info.Width), checked((int)info.Height), path);
    }

    private static byte[] DecodeToRgba(SwatchbinInfo info)
    {
        if (info.RawTextureData.Length == 0)
        {
            throw new InvalidDataException("No texture data found.");
        }

        var format = BcnFormatFor(info.DxgiFormat);
        if (format == CompressionFormat.Unknown)
        {
            return DecodeUncompressed(info);
        }

        var decoder = new BcDecoder();
        var decoded = decoder.DecodeRaw(info.RawTextureData, checked((int)info.Width), checked((int)info.Height), format);
        if (decoded is null || decoded.Length == 0)
        {
            throw new InvalidDataException("BCn decoder returned no pixels.");
        }

        var result = new byte[decoded.Length * 4];
        for (var i = 0; i < decoded.Length; i++)
        {
            result[i * 4 + 0] = decoded[i].r;
            result[i * 4 + 1] = decoded[i].g;
            result[i * 4 + 2] = decoded[i].b;
            result[i * 4 + 3] = decoded[i].a;
        }

        return result;
    }

    private static CompressionFormat BcnFormatFor(uint dxgiFormat) => dxgiFormat switch
    {
        71 or 72 => CompressionFormat.Bc1,
        74 or 75 => CompressionFormat.Bc2,
        77 or 78 => CompressionFormat.Bc3,
        80 or 81 => CompressionFormat.Bc4,
        83 or 84 => CompressionFormat.Bc5,
        98 or 99 => CompressionFormat.Bc7,
        _ => CompressionFormat.Unknown,
    };

    private static byte[] DecodeUncompressed(SwatchbinInfo info)
    {
        var width = checked((int)info.Width);
        var height = checked((int)info.Height);
        var expected = checked(width * height * 4);
        if (info.RawTextureData.Length < expected)
        {
            throw new InvalidDataException($"Expected at least {expected} bytes for {info.DxgiFormatName}; got {info.RawTextureData.Length}.");
        }

        var result = new byte[expected];
        if (info.DxgiFormat is 28 or 29)
        {
            Array.Copy(info.RawTextureData, result, expected);
            return result;
        }

        if (info.DxgiFormat == 87)
        {
            for (var i = 0; i < width * height; i++)
            {
                var idx = i * 4;
                result[idx + 0] = info.RawTextureData[idx + 2];
                result[idx + 1] = info.RawTextureData[idx + 1];
                result[idx + 2] = info.RawTextureData[idx + 0];
                result[idx + 3] = info.RawTextureData[idx + 3];
            }

            return result;
        }

        throw new NotSupportedException($"Unsupported DXGI format: {info.DxgiFormat} ({info.DxgiFormatName}).");
    }

    private static void SaveRgbaPng(byte[] rgba, int width, int height, string path)
    {
        using var bmp = new Bitmap(width, height, PixelFormat.Format32bppArgb);
        var rect = new Rectangle(0, 0, width, height);
        var bitmapData = bmp.LockBits(rect, ImageLockMode.WriteOnly, bmp.PixelFormat);
        try
        {
            var stride = Math.Abs(bitmapData.Stride);
            var bgra = new byte[stride * height];
            for (var y = 0; y < height; y++)
            {
                for (var x = 0; x < width; x++)
                {
                    var src = (y * width + x) * 4;
                    var dst = y * stride + x * 4;
                    bgra[dst + 0] = rgba[src + 2];
                    bgra[dst + 1] = rgba[src + 1];
                    bgra[dst + 2] = rgba[src + 0];
                    bgra[dst + 3] = rgba[src + 3];
                }
            }

            Marshal.Copy(bgra, 0, bitmapData.Scan0, bgra.Length);
        }
        finally
        {
            bmp.UnlockBits(bitmapData);
        }

        bmp.Save(path, ImageFormat.Png);
    }
}
