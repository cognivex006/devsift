export async function load(): Promise<void> {
    try {
        await fetch('https://typescript.example.invalid/items');
    } catch (failure) { }
}
