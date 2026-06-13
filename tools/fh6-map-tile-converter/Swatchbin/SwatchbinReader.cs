using ForzaTools.Bundles;
using ForzaTools.Bundles.Blobs;
using ForzaTools.Bundles.Metadata;
using ForzaTools.Bundles.Metadata.TextureContentHeaders;

namespace ForzaTelemetryTracker.FH6MapTileConverter.Swatchbin;

public sealed class SwatchbinReader
{
    public SwatchbinInfo Load(Stream stream, string fileName)
    {
        var bundle = new Bundle();
        bundle.Load(stream);

        var info = new SwatchbinInfo
        {
            FileName = fileName,
            BundleVersionMajor = bundle.VersionMajor,
            BundleVersionMinor = bundle.VersionMinor,
        };

        var txcbBlob = bundle.Blobs.OfType<TextureContentBlob>().FirstOrDefault()
            ?? throw new InvalidDataException("No TXCB (Texture Content Blob) found in swatchbin file.");

        info.BlobVersionMajor = txcbBlob.VersionMajor;
        info.BlobVersionMinor = txcbBlob.VersionMinor;

        var txchMetadata = txcbBlob.GetMetadataByTag<TextureContentHeaderMetadata>(BundleMetadata.TAG_METADATA_TextureContentHeader)
            ?? throw new InvalidDataException("No TXCH (Texture Content Header) metadata found in TXCB blob.");

        txchMetadata.ParseWithBlobVersion(txcbBlob.VersionMajor, txcbBlob.VersionMinor);

        if (txchMetadata.PCHeader is not null)
        {
            ParsePcHeader(txchMetadata.PCHeader, info);
        }
        else if (txchMetadata.DurangoHeader is not null)
        {
            ParseDurangoHeader(txchMetadata.DurangoHeader, info);
        }
        else
        {
            throw new InvalidDataException("Could not parse texture content header as PC or Durango format.");
        }

        if (txcbBlob.Data is null || txcbBlob.Data.Length == 0)
        {
            throw new InvalidDataException("No texture data found in TXCB blob.");
        }

        info.RawTextureData = txcbBlob.Data;
        return info;
    }

    private static void ParsePcHeader(PCTextureContentHeader header, SwatchbinInfo info)
    {
        info.TextureId = header.Id;
        info.Width = header.Width;
        info.Height = header.Height;
        info.Depth = header.Depth;
        info.MipLevels = header.NumMips;
        info.IsTextureCube = header.IsCubeMap;
        info.IsPremultipliedAlpha = header.IsPremultipliedAlpha;
        info.Transcoding = (TextureTranscoding)(int)header.Transcoding;
        info.ColorProfile = (ColorProfile)(int)header.TargetColorProfile;
        if (header.Slices.Count > 0)
        {
            info.Encoding = (TextureEncoding)(int)header.Slices[0].Encoding;
        }

        info.DxgiFormat = DxgiFormatFor(info.Encoding, info.Transcoding, info.ColorProfile);
        info.DxgiFormatName = DxgiFormatName(info.DxgiFormat);
    }

    private static void ParseDurangoHeader(DurangoTextureContentHeader header, SwatchbinInfo info)
    {
        info.IsDurangoFormat = true;
        info.TextureId = header.Id;
        info.Width = header.Width;
        info.Height = header.Height;
        info.Depth = header.Depth;
        info.MipLevels = header.NumMips;
        info.IsTextureCube = header.IsCubeMap;
        info.IsTexture3D = header.Is3DTexture;
        info.IsPremultipliedAlpha = header.IsPremultipliedAlpha;
        info.Encoding = (TextureEncoding)header.Encoding;
        info.Transcoding = (TextureTranscoding)header.Transcoding;
        info.ColorProfile = (ColorProfile)header.TargetColorProfile;
        info.DxgiFormat = DxgiFormatFor(info.Encoding, info.Transcoding, info.ColorProfile);
        info.DxgiFormatName = DxgiFormatName(info.DxgiFormat);
    }

    private static uint DxgiFormatFor(TextureEncoding encoding, TextureTranscoding transcoding, ColorProfile colorProfile)
    {
        var isSrgb = colorProfile == ColorProfile.Rec709SRgb;
        var encodedFormat = (int)transcoding <= 1 ? (int)encoding : (int)transcoding - 2;

        return encodedFormat switch
        {
            0 => isSrgb ? 72u : 71u,
            1 => isSrgb ? 75u : 74u,
            2 => isSrgb ? 78u : 77u,
            3 => 80u,
            4 => 81u,
            5 => 83u,
            6 => 84u,
            7 => 95u,
            8 => 96u,
            9 => isSrgb ? 99u : 98u,
            10 => 2u,
            11 => 11u,
            12 => 10u,
            13 => isSrgb ? 29u : 28u,
            14 => 85u,
            15 => 86u,
            19 => 61u,
            20 => 65u,
            21 => 49u,
            22 => isSrgb ? 99u : 98u,
            _ => 0u,
        };
    }

    public static string DxgiFormatName(uint format) => format switch
    {
        0 => "DXGI_FORMAT_UNKNOWN",
        2 => "DXGI_FORMAT_R32G32B32A32_FLOAT",
        10 => "DXGI_FORMAT_R16G16B16A16_FLOAT",
        11 => "DXGI_FORMAT_R16G16B16A16_UNORM",
        28 => "DXGI_FORMAT_R8G8B8A8_UNORM",
        29 => "DXGI_FORMAT_R8G8B8A8_UNORM_SRGB",
        49 => "DXGI_FORMAT_R8G8_UNORM",
        61 => "DXGI_FORMAT_R8_UNORM",
        65 => "DXGI_FORMAT_A8_UNORM",
        71 => "DXGI_FORMAT_BC1_UNORM",
        72 => "DXGI_FORMAT_BC1_UNORM_SRGB",
        74 => "DXGI_FORMAT_BC2_UNORM",
        75 => "DXGI_FORMAT_BC2_UNORM_SRGB",
        77 => "DXGI_FORMAT_BC3_UNORM",
        78 => "DXGI_FORMAT_BC3_UNORM_SRGB",
        80 => "DXGI_FORMAT_BC4_UNORM",
        81 => "DXGI_FORMAT_BC4_SNORM",
        83 => "DXGI_FORMAT_BC5_UNORM",
        84 => "DXGI_FORMAT_BC5_SNORM",
        85 => "DXGI_FORMAT_B5G6R5_UNORM",
        86 => "DXGI_FORMAT_B5G5R5A1_UNORM",
        87 => "DXGI_FORMAT_B8G8R8A8_UNORM",
        95 => "DXGI_FORMAT_BC6H_UF16",
        96 => "DXGI_FORMAT_BC6H_SF16",
        98 => "DXGI_FORMAT_BC7_UNORM",
        99 => "DXGI_FORMAT_BC7_UNORM_SRGB",
        _ => $"DXGI_FORMAT_{format}",
    };
}
