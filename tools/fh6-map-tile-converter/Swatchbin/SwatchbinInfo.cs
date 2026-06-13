using System;

namespace ForzaTelemetryTracker.FH6MapTileConverter.Swatchbin;

public sealed class SwatchbinInfo
{
    public string FileName { get; init; } = string.Empty;
    public Guid TextureId { get; set; }
    public uint Width { get; set; }
    public uint Height { get; set; }
    public uint Depth { get; set; }
    public byte MipLevels { get; set; }
    public TextureEncoding Encoding { get; set; }
    public TextureTranscoding Transcoding { get; set; }
    public ColorProfile ColorProfile { get; set; }
    public uint DxgiFormat { get; set; }
    public string DxgiFormatName { get; set; } = string.Empty;
    public bool IsTextureCube { get; set; }
    public bool IsTexture3D { get; set; }
    public bool IsPremultipliedAlpha { get; set; }
    public bool IsDurangoFormat { get; set; }
    public byte BundleVersionMajor { get; set; }
    public byte BundleVersionMinor { get; set; }
    public byte BlobVersionMajor { get; set; }
    public byte BlobVersionMinor { get; set; }
    public byte[] RawTextureData { get; set; } = [];
}

public enum TextureEncoding
{
    Bc1 = 0,
    Bc2 = 1,
    Bc3 = 2,
    UnsignedBc4 = 3,
    SignedBc4 = 4,
    UnsignedBc5 = 5,
    SignedBc5 = 6,
    UnsignedBc6H = 7,
    SignedBc6H = 8,
    Bc7 = 9,
    R32G32B32A32Float = 10,
    R16G16B16A16 = 11,
    R16G16B16A16Float = 12,
    R8G8B8A8 = 13,
    B5G6R5 = 14,
    B5G5R5A1 = 15,
    Dct = 16,
    IntegerDct = 17,
    Procedural = 18,
    R8 = 19,
    A8 = 20,
    R8G8 = 21,
    Bc7HighQuality = 22,
}

public enum TextureTranscoding
{
    None = 0,
    BcBlockRle = 1,
    Bc1 = 2,
    Bc2 = 3,
    Bc3 = 4,
    UnsignedBc4 = 5,
    SignedBc4 = 6,
    UnsignedBc5 = 7,
    SignedBc5 = 8,
    UnsignedBc6H = 9,
    SignedBc6H = 10,
    Bc7 = 11,
}

public enum ColorProfile
{
    Rec709Linear = 0,
    Rec709SRgb = 1,
    Rec709Gamma2 = 2,
    XvYccLinear = 3,
}
