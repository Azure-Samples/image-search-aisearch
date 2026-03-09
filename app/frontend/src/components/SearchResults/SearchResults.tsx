import { useState, useEffect } from "react";
import { Gallery, Image } from "react-grid-gallery";

interface Props {
    images: string[]
}

export const SearchResults = ({ images }: Props) => {
    const [galleryImages, setGalleryImages] = useState<Image[]>([]);

    useEffect(() => {
        let cancelled = false;

        const loadImageDimensions = async () => {
            const loadedImages = await Promise.all(
                images.map(src => 
                    new Promise<Image>((resolve) => {
                        const img = new window.Image();
                        img.onload = () => {
                            resolve({
                                src,
                                width: img.naturalWidth,
                                height: img.naturalHeight
                            });
                        };
                        img.onerror = () => {
                            // Fallback for failed loads
                            resolve({ src, width: 128, height: 128 });
                        };
                        img.src = src;
                    })
                )
            );
            if (!cancelled) {
                setGalleryImages(loadedImages);
            }
        };

        loadImageDimensions();

        return () => { cancelled = true; };
    }, [images]);

    if (galleryImages.length === 0 && images.length > 0) {
        return <div>Loading images...</div>;
    }

    return (
        <Gallery images={galleryImages} enableImageSelection={false} />
    );
};