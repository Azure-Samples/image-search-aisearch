import { useState } from "react";
import { Gallery } from "react-grid-gallery";

import styles from "./SearchResults.module.css";

interface Props {
    images: string[]
}

export const SearchResults = ({ images }: Props) => {
    const galleryImages = images.map(val => ({
        src: val,
        width: 128,
        height: 128
    }))
    return (
        <Gallery images={galleryImages} enableImageSelection={false} />
    );
};