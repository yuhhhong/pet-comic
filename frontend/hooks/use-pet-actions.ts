"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { describeError } from "@/lib/api-client";
import { deletePet, retryCharacterCard, retryPet, trashPet, updatePet, type PetDetail } from "@/lib/pets";

export function usePetActions(petId: string) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [actionError, setActionError] = useState<string | null>(null);
  const reportError = (error: unknown) => setActionError(describeError(error));
  const clearActionError = () => setActionError(null);

  function publish(pet: PetDetail) {
    queryClient.setQueryData(["pet", pet.pet_id], pet);
    void queryClient.invalidateQueries({ queryKey: ["pets"] });
    setActionError(pet.error?.message ?? null);
  }

  const save = useMutation({
    mutationFn: (body: { name: string; personality: string }) => updatePet(petId, body),
    onSuccess: publish,
    onError: reportError,
  });
  const retry = useMutation({
    mutationFn: () => retryPet(petId),
    onSuccess: publish,
    onError: reportError,
  });
  const retryCard = useMutation({
    mutationFn: () => retryCharacterCard(petId),
    onSuccess: publish,
    onError: reportError,
  });
  const setEnabled = useMutation({
    mutationFn: (enabled: boolean) => updatePet(petId, { enabled }),
    onSuccess: publish,
    onError: reportError,
  });
  const trash = useMutation({
    mutationFn: () => trashPet(petId),
    onSuccess: publish,
    onError: reportError,
  });
  const remove = useMutation({
    mutationFn: () => deletePet(petId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["pets"] });
      router.push("/pets");
    },
    onError: reportError,
  });
  const busy = save.isPending || retry.isPending || retryCard.isPending || setEnabled.isPending || trash.isPending || remove.isPending;

  return { save, retry, retryCard, setEnabled, trash, remove, busy, actionError, clearActionError };
}
